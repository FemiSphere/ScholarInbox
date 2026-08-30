from __future__ import annotations

import base64
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

from .models import EmailMessage
from .telemetry import RunMetrics


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailDependencyError(RuntimeError):
    pass


class GmailAuthenticationError(RuntimeError):
    pass


class GmailConnectionError(RuntimeError):
    pass


class GmailClient:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        base_dir: Path | None = None,
        metrics: RunMetrics | None = None,
    ) -> None:
        self.config = config
        self.base_dir = base_dir or Path.cwd()
        self.gmail_config = config["gmail"]
        self.parsing_config = config["parsing"]
        self.metrics = metrics
        self._service = None

    @property
    def credentials_path(self) -> Path:
        return self._resolve(self.gmail_config.get("credentials_path", "credentials.json"))

    @property
    def token_path(self) -> Path:
        return self._resolve(self.gmail_config.get("token_path", "token.json"))

    def reauthorize(self) -> Path:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:  # pragma: no cover - depends on user env
            raise GmailDependencyError(
                "Google Gmail dependencies are missing. Install with `python -m pip install -e .`."
            ) from exc

        if self.token_path.exists():
            backup_path = self.token_path.with_name(
                f"{self.token_path.stem}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{self.token_path.suffix}"
            )
            self.token_path.rename(backup_path)

        try:
            creds = self._authorize_with_browser(InstalledAppFlow)
        except (OSError, TimeoutError) as exc:
            raise GmailConnectionError(_connection_error_message("authorizing Gmail OAuth")) from exc
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        self._service = None
        return self.token_path

    def fetch_unread_emails(self, *, max_results: int | None = None) -> list[EmailMessage]:
        service = self._get_service()
        query = self.gmail_config.get("query", "is:unread")
        limit = max_results or int(self.gmail_config.get("max_emails_per_run", 50))
        include_spam_trash = bool(self.gmail_config.get("include_spam_trash", False))
        request = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=limit,
                includeSpamTrash=include_spam_trash,
            )
        )
        response = self._execute(
            request,
            "searching unread Gmail messages",
            metric_operation="list_messages",
        )
        messages = response.get("messages", [])
        message_ids = [message["id"] for message in messages]
        return self._fetch_emails(message_ids)

    def fetch_email(self, message_id: str) -> EmailMessage:
        service = self._get_service()
        request = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
        )
        message = self._execute(
            request,
            f"fetching Gmail message {message_id}",
            metric_operation="get_message",
        )
        return self._email_from_message(message_id, message)

    def _email_from_message(self, message_id: str, message: dict[str, Any]) -> EmailMessage:
        headers = {
            header["name"].lower(): header.get("value", "")
            for header in message.get("payload", {}).get("headers", [])
        }
        html_parts: list[str] = []
        text_parts: list[str] = []
        image_paths: list[Path] = []
        cid_map: dict[str, Path] = {}
        save_images = not _is_google_scholar_headers(
            headers.get("from", ""),
            headers.get("subject", ""),
        )
        self._walk_parts(
            message_id=message_id,
            part=message.get("payload", {}),
            html_parts=html_parts,
            text_parts=text_parts,
            image_paths=image_paths,
            cid_map=cid_map,
            save_images=save_images,
        )
        html = "\n".join(html_parts)
        for cid, path in cid_map.items():
            html = html.replace(f"cid:{cid}", str(path))
            html = html.replace(f"cid:<{cid}>", str(path))
        return EmailMessage(
            id=message_id,
            thread_id=message.get("threadId", ""),
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            date=_parse_email_date(headers.get("date", "")),
            html=html,
            text="\n".join(text_parts),
            snippet=message.get("snippet", ""),
            labels=list(message.get("labelIds", [])),
            image_paths=image_paths,
        )

    def mark_as_read(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        service = self._get_service()
        batch_size = max(1, min(1000, int(self.gmail_config.get("batch_modify_size", 1000))))
        for offset in range(0, len(message_ids), batch_size):
            chunk = message_ids[offset : offset + batch_size]
            request = service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "removeLabelIds": ["UNREAD"]},
            )
            self._execute(
                request,
                f"marking {len(chunk)} Gmail messages as read",
                metric_operation="batch_mark_read",
                metric_item_count=len(chunk),
            )

    def _fetch_emails(self, message_ids: list[str]) -> list[EmailMessage]:
        if not message_ids:
            return []
        batch_size = max(1, min(100, int(self.gmail_config.get("batch_fetch_size", 10))))
        service = self._get_service()
        if batch_size == 1 or not hasattr(service, "new_batch_http_request"):
            return [self.fetch_email(message_id) for message_id in message_ids]

        messages_by_id: dict[str, dict[str, Any]] = {}
        max_retries = max(0, int(self.gmail_config.get("batch_fetch_max_retries", 3)))
        retry_backoff = max(
            0.0,
            float(self.gmail_config.get("batch_fetch_retry_backoff_seconds", 1.0)),
        )
        for offset in range(0, len(message_ids), batch_size):
            chunk = message_ids[offset : offset + batch_size]
            pending = list(chunk)
            for attempt in range(max_retries + 1):
                failures: dict[str, BaseException] = {}

                def callback(request_id, response, exception):
                    request_key = str(request_id)
                    if exception is not None:
                        failures[request_key] = exception
                    elif isinstance(response, dict):
                        messages_by_id[request_key] = response

                batch = service.new_batch_http_request(callback=callback)
                for message_id in pending:
                    request = service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="full",
                    )
                    batch.add(request, request_id=message_id)
                self._execute_batch(batch, item_count=len(pending))

                permanent = {
                    message_id: exception
                    for message_id, exception in failures.items()
                    if not _is_retryable_batch_error(exception)
                }
                if permanent:
                    raise GmailConnectionError(_batch_failure_message(permanent, exhausted=False))

                pending = list(failures)
                if not pending:
                    break
                if attempt >= max_retries:
                    raise GmailConnectionError(_batch_failure_message(failures, exhausted=True))

                delay = _batch_retry_delay(
                    failures.values(),
                    fallback=retry_backoff * (2**attempt),
                )
                if delay > 0:
                    sleep(delay)

        missing = [message_id for message_id in message_ids if message_id not in messages_by_id]
        if missing:
            missing_ids = ", ".join(missing)[:240]
            raise GmailConnectionError(f"Gmail batch message fetch returned no response for: {missing_ids}")
        return [self._email_from_message(message_id, messages_by_id[message_id]) for message_id in message_ids]

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.auth.exceptions import RefreshError
            from google.oauth2.credentials import Credentials
            from google_auth_httplib2 import AuthorizedHttp
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            import httplib2
        except ImportError as exc:  # pragma: no cover - depends on user env
            raise GmailDependencyError(
                "Google Gmail dependencies are missing. Install with `python -m pip install -e .`."
            ) from exc

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), GMAIL_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    if not _is_invalid_grant_error(exc):
                        raise GmailAuthenticationError(
                            "Gmail OAuth token refresh failed. Check network connectivity and OAuth configuration."
                        ) from exc
                    creds = None
                except (OSError, TimeoutError) as exc:
                    raise GmailConnectionError(_connection_error_message("refreshing Gmail OAuth token")) from exc
            if not creds or not creds.valid:
                creds = self._authorize_with_browser(InstalledAppFlow)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        timeout_seconds = int(self.gmail_config.get("request_timeout_seconds", 30))
        http = httplib2.Http(timeout=timeout_seconds, proxy_info=_proxy_info(httplib2, self.gmail_config))
        self._service = build("gmail", "v1", http=AuthorizedHttp(creds, http=http))
        return self._service

    def _authorize_with_browser(self, installed_app_flow):
        if not self.credentials_path.exists():
            raise FileNotFoundError(f"Gmail credentials not found: {self.credentials_path}")
        flow = installed_app_flow.from_client_secrets_file(str(self.credentials_path), GMAIL_SCOPES)
        return flow.run_local_server(port=0)

    def _execute(
        self,
        request,
        action: str,
        *,
        metric_operation: str = "gmail_request",
        metric_item_count: int = 1,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        try:
            response = request.execute()
        except TimeoutError as exc:
            self._record_request(metric_operation, metric_item_count, started_at, "timeout")
            raise GmailConnectionError(_connection_error_message(action)) from exc
        except OSError as exc:
            self._record_request(metric_operation, metric_item_count, started_at, "network_error")
            raise GmailConnectionError(_connection_error_message(action, detail=str(exc))) from exc
        self._record_request(metric_operation, metric_item_count, started_at, "ok")
        return response

    def _execute_batch(self, batch, *, item_count: int) -> None:
        started_at = perf_counter()
        try:
            batch.execute()
        except TimeoutError as exc:
            self._record_request("batch_get_messages", item_count, started_at, "timeout")
            raise GmailConnectionError(_connection_error_message("batch fetching Gmail messages")) from exc
        except OSError as exc:
            self._record_request("batch_get_messages", item_count, started_at, "network_error")
            raise GmailConnectionError(
                _connection_error_message("batch fetching Gmail messages", detail=str(exc))
            ) from exc
        self._record_request("batch_get_messages", item_count, started_at, "ok")

    def _record_request(self, operation: str, item_count: int, started_at: float, status: str) -> None:
        if self.metrics is None:
            return
        self.metrics.record_io_request(
            operation=operation,
            item_count=item_count,
            elapsed_seconds=perf_counter() - started_at,
            status=status,
        )

    def _walk_parts(
        self,
        *,
        message_id: str,
        part: dict[str, Any],
        html_parts: list[str],
        text_parts: list[str],
        image_paths: list[Path],
        cid_map: dict[str, Path],
        save_images: bool,
    ) -> None:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})
        headers = {
            header["name"].lower(): header.get("value", "")
            for header in part.get("headers", [])
        }

        if "parts" in part:
            for child in part["parts"]:
                self._walk_parts(
                    message_id=message_id,
                    part=child,
                    html_parts=html_parts,
                    text_parts=text_parts,
                    image_paths=image_paths,
                    cid_map=cid_map,
                    save_images=save_images,
                )
            return

        if mime_type == "text/html":
            html_parts.append(_decode_body_data(body.get("data", "")))
        elif mime_type == "text/plain":
            text_parts.append(_decode_body_data(body.get("data", "")))
        elif save_images and mime_type.startswith("image/") and self.parsing_config.get("save_toc_images", True):
            if not _is_likely_toc_image(filename, headers):
                return
            if len(image_paths) >= int(self.parsing_config.get("max_images_per_email", 20)):
                return
            data = self._read_part_bytes(message_id, body)
            if not data:
                return
            suffix = _image_suffix(mime_type, filename)
            safe_name = _safe_filename(filename) or f"{message_id}_{len(image_paths) + 1}{suffix}"
            target_dir = self._image_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / safe_name
            target.write_bytes(data)
            image_paths.append(target)
            content_id = headers.get("content-id", "").strip("<>")
            if content_id:
                cid_map[content_id] = target

    def _read_part_bytes(self, message_id: str, body: dict[str, Any]) -> bytes:
        if body.get("data"):
            return _decode_body_bytes(body["data"])
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            return b""
        service = self._get_service()
        request = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
        )
        attachment = self._execute(
            request,
            f"fetching Gmail attachment {attachment_id}",
            metric_operation="get_attachment",
        )
        return _decode_body_bytes(attachment.get("data", ""))

    def _image_dir(self) -> Path:
        root = self._resolve(self.parsing_config.get("toc_image_dir", "data/toc_images"))
        return root / datetime.now().strftime("%Y-%m-%d")

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.base_dir / path


def _decode_body_data(value: str) -> str:
    return _decode_body_bytes(value).decode("utf-8", errors="replace")


def _decode_body_bytes(value: str) -> bytes:
    if not value:
        return b""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _parse_email_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._")
    return cleaned[:120]


def _image_suffix(mime_type: str, filename: str) -> str:
    if "." in filename:
        return ""
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(mime_type.lower(), ".img")


def _is_google_scholar_headers(sender: str, subject: str) -> bool:
    searchable = f"{sender} {subject}".lower()
    return (
        "scholaralerts-noreply@google.com" in searchable
        or "google scholar" in searchable
        or "google 学术" in searchable
        or "google 學術" in searchable
    )


def _is_invalid_grant_error(exc: BaseException) -> bool:
    text = " ".join(str(part) for part in (getattr(exc, "args", None) or [exc])).lower()
    return "invalid_grant" in text or "expired or revoked" in text


def _connection_error_message(action: str, detail: str | None = None) -> str:
    message = (
        f"Gmail connection failed while {action}. "
        "Check network access to Google/Gmail API, VPN or proxy settings, then retry. "
        "For local-only verification, run `文献 --dry-run --sample`."
    )
    if detail:
        message += f" Detail: {detail}"
    return message


def _is_retryable_batch_error(exception: BaseException) -> bool:
    status = getattr(getattr(exception, "resp", None), "status", None)
    return status in {429, 500, 502, 503, 504} or isinstance(exception, (OSError, TimeoutError))


def _batch_retry_delay(exceptions, *, fallback: float) -> float:
    retry_after = 0.0
    for exception in exceptions:
        response = getattr(exception, "resp", None)
        if response is None or not hasattr(response, "get"):
            continue
        try:
            retry_after = max(retry_after, float(response.get("retry-after", 0) or 0))
        except (TypeError, ValueError):
            continue
    return min(30.0, max(retry_after, fallback))


def _batch_failure_message(
    failures: dict[str, BaseException],
    *,
    exhausted: bool,
) -> str:
    first_exception = next(iter(failures.values()))
    status = getattr(getattr(first_exception, "resp", None), "status", None)
    reason = getattr(first_exception, "reason", None) or type(first_exception).__name__
    failed_ids = ", ".join(failures)[:180]
    stage = "after retrying" if exhausted else "with a non-retryable error"
    status_text = f"HTTP {status}: " if status is not None else ""
    return (
        f"Gmail batch message fetch failed {stage} for {len(failures)} request(s): "
        f"{status_text}{reason}. Message IDs: {failed_ids}"
    )


def _proxy_info(httplib2_module, gmail_config: dict[str, Any]):
    proxy_url = (
        gmail_config.get("proxy_url")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("CODEX_PROXY_URL")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("CODEX_ALL_PROXY_URL")
    )
    if not proxy_url:
        return None

    noproxy = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or os.environ.get("CODEX_NO_PROXY")
    return httplib2_module.proxy_info_from_url(proxy_url, "https", noproxy=noproxy)


def _is_likely_toc_image(filename: str, headers: dict[str, str]) -> bool:
    searchable = " ".join([filename, headers.get("content-id", ""), headers.get("content-description", "")]).lower()
    blocked = (
        "logo",
        "icon",
        "social",
        "twitter",
        "facebook",
        "linkedin",
        "tracking",
        "pixel",
        "spacer",
        "avatar",
        "profile",
    )
    if any(token in searchable for token in blocked):
        return False
    if any(token in searchable for token in ("toc", "graphical", "abstract", "figure", "image", "ga", "scheme")):
        return True
    return not filename

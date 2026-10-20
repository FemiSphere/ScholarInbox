"""Lossless, ordered email regions for bounded LLM extraction.

Article heuristics choose boundaries only: the model sees every retained region,
including formats for which no article-title heuristic matches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Callable


@dataclass
class Atom:
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    article_start: bool = False
    boundary: bool = False
    row: int | None = None


@dataclass
class EmailChunk:
    atoms: list[Atom]

    @property
    def text(self) -> str:
        return "\n".join(atom.text for atom in self.atoms)

    @property
    def links(self) -> list[tuple[str, str]]:
        return list(dict.fromkeys(link for atom in self.atoms for link in atom.links))

    @property
    def images(self) -> list[str]:
        return list(dict.fromkeys(image for atom in self.atoms for image in atom.images))


class OrderedEmailParser(HTMLParser):
    def __init__(self, is_article: Callable[[str, str], bool]):
        super().__init__(convert_charrefs=True)
        self.atoms: list[Atom] = []
        self.is_article = is_article
        self.ignored = 0
        self.anchor: tuple[str, list[str]] | None = None
        self.heading = False
        self.article_depth = 0
        self.pending_boundary = False
        self.rows: list[int] = []
        self.row_counter = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag in {"style", "script", "noscript"}:
            self.ignored += 1
        if self.ignored:
            return
        if tag == "tr":
            self.row_counter += 1
            self.rows.append(self.row_counter)
        if tag == "article":
            self.pending_boundary = True
        if tag in {"article", "li", "tr"}:
            self.article_depth += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = True
        if tag == "a":
            self._flush_anchor()
            self.anchor = (attrs.get("href", "") or "", [])
        if tag == "img":
            src = attrs.get("src", "") or ""
            alt = re.sub(r"\s+", " ", attrs.get("alt", "") or "").strip()
            if self.anchor is not None and alt:
                self.anchor[1].append(alt)
            if src:
                self.atoms.append(Atom(f"[IMAGE src={src} alt={alt}]", images=[src],
                                       boundary=self.pending_boundary, row=self.rows[-1] if self.rows else None))
                self.pending_boundary = False

    def handle_data(self, data):
        if self.ignored:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self.anchor is not None:
            self.anchor[1].append(text)
        else:
            self.atoms.append(Atom(text, boundary=self.pending_boundary, row=self.rows[-1] if self.rows else None))
            self.pending_boundary = False

    def _flush_anchor(self):
        if self.anchor is None:
            return
        href, pieces = self.anchor
        title = " ".join(pieces)
        if title or href:
            title = title or "[image or empty link]"
            start = self.is_article(title, href)
            self.atoms.append(Atom(f"[LINK href={href}] {title}", [(href, title)] if href else [],
                                   article_start=start, boundary=self.pending_boundary,
                                   row=self.rows[-1] if self.rows else None))
            self.pending_boundary = False
        self.anchor = None

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"style", "script", "noscript"} and self.ignored:
            self.ignored -= 1
            return
        if self.ignored:
            return
        if tag == "a":
            self._flush_anchor()
        if tag == "tr" and self.rows:
            self.rows.pop()
        if tag in {"article", "li", "tr"}:
            self.article_depth = max(0, self.article_depth - 1)
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = False

    def close(self):
        super().close()
        self._flush_anchor()


def _text_windows(text: str, limit: int, overlap: int = 160) -> list[str]:
    overlap = min(overlap, max(0, limit // 5))
    windows = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        windows.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return windows


def build_email_chunks(*, html: str, text: str, image_paths: list[str],
                       is_article: Callable[[str, str], bool],
                       accept_link: Callable[[str, str], bool], accept_image: Callable[[str], bool],
                       text_max_chars: int, max_links: int, max_images: int,
                       max_items: int) -> list[EmailChunk]:
    limit = max(1, text_max_chars)
    if html:
        parser = OrderedEmailParser(is_article)
        parser.feed(html)
        parser.close()
        atoms = parser.atoms
    else:
        atoms = [Atom(line.strip(), article_start=is_article(line.strip(), ""))
                 for line in text.splitlines() if line.strip()]
    seen_images = {image for atom in atoms for image in atom.images}
    atoms.extend(Atom(f"[IMAGE src={image}]", images=[image]) for image in image_paths if image not in seen_images)
    filtered = []
    for atom in atoms:
        links = [link for link in atom.links if accept_link(*link)]
        images = [image for image in atom.images if accept_image(image)]
        # Pure footer/management links and tracking images carry no article information.
        if atom.links and not links or atom.images and not images:
            continue
        if max_links <= 0:
            links = []
        if max_images <= 0:
            images = []
        if len(atom.text) <= limit:
            filtered.append(Atom(atom.text, links, images, atom.article_start, atom.boundary, atom.row))
        else:
            for index, window in enumerate(_text_windows(atom.text, limit)):
                filtered.append(Atom(window, links, images, atom.article_start and index == 0, atom.boundary and index == 0, atom.row))
    # Pack whole article regions where possible; oversized regions are partitioned in order.
    regions: list[list[Atom]] = []
    article_rows = {atom.row for atom in filtered if atom.article_start and atom.row is not None}
    previous_row = None
    for atom in filtered:
        # A row containing a scientific title owns its preceding thumbnail too.
        # Rows without titles remain weak layout structure and consume no item count.
        row_start = atom.row in article_rows and atom.row != previous_row
        if (not regions or atom.boundary or row_start
                or (atom.article_start and any(item.article_start for item in regions[-1]))):
            regions.append([])
        regions[-1].append(atom)
        previous_row = atom.row
    unknown_format = not any(atom.article_start for atom in filtered)
    chunks: list[EmailChunk] = []
    current: list[Atom] = []

    def fits(candidate):
        chunk = EmailChunk(candidate)
        return (len(chunk.text) <= limit and len(chunk.links) <= max(0, max_links)
                and len(chunk.images) <= max(0, max_images)
                and sum(atom.article_start for atom in candidate) <= max(1, max_items))

    for region in regions:
        if fits(current + region):
            current += region
            continue
        if current:
            chunks.append(EmailChunk(current))
            current = []
        # Repeat context only for a region with one unambiguous article title.
        # This lets AI attribute the tail of a long abstract to its own article.
        region_chunk = EmailChunk(region)
        titles = [link for link in region_chunk.links if is_article(link[1], link[0])]
        context = None
        if not fits(region) and len(titles) == 1 and max_links > 0:
            href, title = titles[0]
            context_text = f"[ARTICLE_CONTEXT] {title} ({href})"
            if len(context_text) < limit // 2:
                context = Atom(context_text, links=[titles[0]],
                               images=region_chunk.images if len(region_chunk.images) <= max_images else [])
        if context is not None:
            room = limit - len(context.text) - 1
            fragments = []
            for atom in region:
                windows = _text_windows(atom.text, room) if len(atom.text) > room else [atom.text]
                fragments.extend(Atom(window, atom.links, atom.images, atom.article_start and index == 0)
                                 for index, window in enumerate(windows))
            region = fragments
            current = [context]
        for atom in region:
            if current and not fits(current + [atom]):
                # A single context consumes at most half the size budget, so every
                # text fragment still fits and no content or candidate is dropped.
                previous = EmailChunk(current)
                chunks.append(previous)
                current = [context] if context is not None and fits([context, atom]) else []
                if unknown_format and context is None:
                    overlap = Atom("[PREVIOUS_REGION_OVERLAP] " + previous.text[-min(160, limit // 8):])
                    if fits([overlap, atom]):
                        current.append(overlap)
            current.append(atom)
        if context is not None and current:
            chunks.append(EmailChunk(current))
            current = []
    if current:
        chunks.append(EmailChunk(current))
    return chunks


def split_email_chunk(chunk: EmailChunk) -> list[EmailChunk]:
    """Prefer article boundaries, then ordered atoms, then overlapping text halves."""
    boundaries = []
    for index, atom in enumerate(chunk.atoms):
        if not atom.article_start:
            continue
        start = index
        if atom.row is not None:
            while start and chunk.atoms[start - 1].row == atom.row:
                start -= 1
        else:
            # Explicit article containers may begin with a thumbnail before a title.
            for candidate in range(index - 1, -1, -1):
                previous = chunk.atoms[candidate]
                if previous.article_start:
                    break
                if previous.boundary:
                    start = candidate
                    break
        if start and start not in boundaries:
            boundaries.append(start)
    if boundaries:
        middle = min(boundaries, key=lambda index: abs(index - len(chunk.atoms) / 2))
        return [EmailChunk(chunk.atoms[:middle]), EmailChunk(chunk.atoms[middle:])]
    if len(chunk.atoms) > 1:
        middle = len(chunk.atoms) // 2
        children = [EmailChunk(chunk.atoms[:middle]), EmailChunk(chunk.atoms[middle:])]
        if len(chunk.links) == 1:
            href, title = chunk.links[0]
            context = Atom(f"[ARTICLE_CONTEXT] {title} ({href})", links=chunk.links, images=chunk.images)
            if len(context.text) < len(chunk.text) // 3:
                children = [EmailChunk([context] + child.atoms) if not child.links else child for child in children]
        return children
    atom = chunk.atoms[0]
    if len(atom.text) <= 256:
        return []
    limit = (len(atom.text) + 1) // 2 + min(80, len(atom.text) // 10)
    return [EmailChunk([Atom(window, atom.links, atom.images, atom.article_start)])
            for window in _text_windows(atom.text, limit, overlap=80)]

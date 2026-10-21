import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from literature_digest.evidence_cache import CacheError, EvidenceCache


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


def test_positive_and_negative_expire_at_separate_ttls(tmp_path):
    clock = Clock()
    with EvidenceCache(tmp_path / 'cache.sqlite3', clock=clock, ttl_days=1, negative_ttl_hours=1) as cache:
        cache.put('doi:1', {'abstract': 'Reliable source abstract'})
        cache.put('doi:2', {'status': 'missing'}, negative=True)
        clock.value += 3601
        assert cache.get('doi:1')['abstract'] == 'Reliable source abstract'
        assert cache.get('doi:2') is None
        clock.value += 86400
        assert cache.get('doi:1') is None


def test_lru_eviction_prefers_recently_accessed_records(tmp_path):
    clock = Clock()
    with EvidenceCache(tmp_path / 'cache.sqlite3', max_entries=2, clock=clock) as cache:
        cache.put('first', {'abstract': 'first'})
        cache.put('second', {'abstract': 'second'})
        cache.get('first')
        cache.put('third', {'abstract': 'third'})
        assert cache.get('first') is not None
        assert cache.get('second') is None
        assert cache.get('third') is not None


def test_reopen_prunes_expired_rows(tmp_path):
    clock = Clock()
    path = tmp_path / 'cache.sqlite3'
    with EvidenceCache(path, clock=clock, ttl_days=1) as cache:
        cache.put('old', {'abstract': 'old'})
    clock.value += 86401
    with EvidenceCache(path, clock=clock) as cache:
        assert cache.get('old') is None
        assert cache._db().execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 0


def test_rejects_oversized_records_and_raw_pages(tmp_path):
    with EvidenceCache(tmp_path / 'cache.sqlite3') as cache:
        assert not cache.put('large', {'abstract': 'a' * 32768})
        assert not cache.put('raw', {'content': '<html>full page</html>'})
        assert not cache.put('nested', {'evidence': {'raw_html': '<html>full page</html>'}})
        assert not cache.put('invalid', {'value': float('nan')})
        assert cache.put('small', {'status': 'ok', 'evidence': {'abstract': '摘要', 'source_url': 'https://example.org/paper'}})
        assert cache.get('small')['evidence']['abstract'] == '摘要'


def test_capacity_bounds_file_after_many_large_replacements(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    budget = 96 * 1024
    with EvidenceCache(path, max_bytes=budget, max_entries=10) as cache:
        for index in range(60):
            cache.put(f'paper-{index}', {'abstract': chr(65 + index % 26) * 15000})
            assert path.stat().st_size <= budget
        assert cache._db().execute('SELECT COUNT(*) FROM evidence').fetchone()[0] <= 10
        assert cache.get('paper-59') is not None
    assert path.stat().st_size <= budget
    assert {p.name for p in tmp_path.iterdir()} == {'cache.sqlite3'}


def test_lowered_capacity_compacts_existing_cache(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    with EvidenceCache(path) as cache:
        for index in range(30):
            cache.put(str(index), {'abstract': 'x' * 30000})
    assert path.stat().st_size > 64 * 1024
    with EvidenceCache(path, max_bytes=64 * 1024, max_entries=2) as cache:
        assert path.stat().st_size <= 64 * 1024
        assert cache._db().execute('SELECT COUNT(*) FROM evidence').fetchone()[0] <= 2


def test_concurrent_writers_share_one_file_without_sidecars(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    with EvidenceCache(path, max_entries=20) as cache:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda i: cache.put(str(i), {'abstract': f'paper {i}'}), range(60)))
        assert cache._db().execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 20
    assert {p.name for p in tmp_path.iterdir()} == {'cache.sqlite3'}
    with EvidenceCache(path) as cache:
        assert cache.get('59') is not None


def test_interrupted_transaction_rolls_back_and_closes_cleanly(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    with pytest.raises(KeyboardInterrupt):
        with EvidenceCache(path) as cache:
            cache.put('preserved', {'abstract': 'committed'})
            with cache._transaction() as db:
                db.execute('DELETE FROM evidence')
                raise KeyboardInterrupt
    assert {p.name for p in tmp_path.iterdir()} == {'cache.sqlite3'}
    with EvidenceCache(path) as cache:
        assert cache.get('preserved') == {'abstract': 'committed'}


def test_corrupt_database_is_not_replaced(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    original = b'user-data-not-a-sqlite-database'
    path.write_bytes(original)
    with pytest.raises(CacheError):
        EvidenceCache(path)
    assert path.read_bytes() == original
    assert {p.name for p in tmp_path.iterdir()} == {'cache.sqlite3'}


def test_other_sqlite_database_is_not_modified(tmp_path):
    path = tmp_path / 'cache.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE user_data (value TEXT)')
        db.execute('INSERT INTO user_data VALUES (?)', ('keep this',))
    original = path.read_bytes()
    with pytest.raises(CacheError, match='Unrecognized'):
        EvidenceCache(path)
    assert path.read_bytes() == original
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT value FROM user_data').fetchone()[0] == 'keep this'


def test_context_closes_and_double_close_is_safe(tmp_path):
    with EvidenceCache(tmp_path / 'cache.sqlite3') as cache:
        cache.put('a', {'abstract': 'a'})
    cache.close()
    with pytest.raises(CacheError, match='closed'):
        cache.get('a')


def test_zero_ttl_does_not_persist_and_small_budget_is_rejected(tmp_path):
    with EvidenceCache(tmp_path / 'cache.sqlite3', ttl_days=0, negative_ttl_hours=0) as cache:
        assert not cache.put('a', {'abstract': 'a'})
        assert not cache.put('b', {'status': 'missing'}, negative=True)
    with pytest.raises(ValueError):
        EvidenceCache(tmp_path / 'small.sqlite3', max_bytes=100)


def test_lru_remains_ordered_after_reopen_with_same_clock(tmp_path):
    clock = Clock()
    path = tmp_path / 'cache.sqlite3'
    with EvidenceCache(path, clock=clock, max_entries=2) as cache:
        cache.put('first', {'abstract': 'one'})
        cache.put('second', {'abstract': 'two'})
    with EvidenceCache(path, clock=clock, max_entries=2) as cache:
        cache.put('third', {'abstract': 'three'})
        assert cache.get('third') is not None
        assert cache.get('first') is None

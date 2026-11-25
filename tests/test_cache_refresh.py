"""The live app must pick up new data files without a restart.

Streamlit leaves arguments whose names start with "_" out of the cache key, so a "data version"
argument named like that silently freezes the cache. These tests catch that regression.
"""
from dashboard import common as C
from tracker import config


def test_database_rebuild_reruns_when_inputs_change(monkeypatch, tmp_path):
    db = tmp_path / "tracker.db"
    db.write_text("")
    monkeypatch.setattr(config, "DB_PATH", db)
    calls = []
    monkeypatch.setattr(C.build, "ensure_database", lambda log=None: calls.append(1))
    C._ensure_db.clear()
    C._ensure_db(1.0)
    C._ensure_db(1.0)
    C._ensure_db(2.0)              # newer input files → must check / rebuild again
    assert len(calls) == 2
    C._ensure_db.clear()


def test_query_cache_is_keyed_on_database_version(monkeypatch):
    calls = []
    monkeypatch.setattr(C.db, "read_sql", lambda sql, params: calls.append(sql) or C.pd.DataFrame())
    C._q.clear()
    C._q("SELECT 1", (), 1.0)
    C._q("SELECT 1", (), 1.0)
    C._q("SELECT 1", (), 2.0)      # rebuilt database → must re-query
    assert len(calls) == 2
    C._q.clear()

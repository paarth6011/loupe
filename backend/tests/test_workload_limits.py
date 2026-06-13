"""Auto-created workload behaviour: idempotency, the cardinality cap (N3), and
recovery from a concurrent first-write (M2)."""

import pytest
from fastapi import HTTPException

from app.models import Workload
from app.routers.metrics import _get_or_create_workload


def test_get_or_create_is_idempotent(db_session, account_id):
    first = _get_or_create_workload(db_session, "same", account_id, max_workloads=0)
    db_session.flush()
    again = _get_or_create_workload(db_session, "same", account_id, max_workloads=0)
    assert first.id == again.id
    count = db_session.query(Workload).filter(Workload.name == "same").count()
    assert count == 1


def test_cardinality_cap_blocks_new_workloads(db_session, account_id):
    _get_or_create_workload(db_session, "a", account_id, max_workloads=2)
    _get_or_create_workload(db_session, "b", account_id, max_workloads=2)
    with pytest.raises(HTTPException) as exc:
        _get_or_create_workload(db_session, "c", account_id, max_workloads=2)
    assert exc.value.status_code == 429
    # The cap never blocks an *existing* workload from resolving.
    existing = _get_or_create_workload(db_session, "a", account_id, max_workloads=2)
    assert existing.name == "a"


def test_cardinality_cap_disabled_with_zero(db_session, account_id):
    for name in "abcdef":
        _get_or_create_workload(db_session, name, account_id, max_workloads=0)
    assert db_session.query(Workload).count() == 6


def test_get_or_create_recovers_from_lost_insert_race(
    db_session, account_id, monkeypatch
):
    """If a concurrent ingest inserts the same new name between our SELECT-miss
    and our INSERT, the unique constraint rejects ours; the helper must recover
    by re-reading the winner instead of surfacing the IntegrityError as a 500."""
    # Pre-create the "winner" the way a concurrent ingest would have. We then
    # force only the helper's *first* lookup to miss it, so its INSERT collides
    # with the unique constraint and exercises the recovery re-read.
    winner = Workload(account_id=account_id, name="raced")
    db_session.add(winner)
    db_session.flush()

    original_scalars = db_session.scalars
    calls = {"n": 0}

    class _EmptyResult:
        def first(self):
            return None

    def fake_scalars(stmt):
        calls["n"] += 1
        if calls["n"] == 1:  # first in-function SELECT misses
            return _EmptyResult()
        return original_scalars(stmt)

    monkeypatch.setattr(db_session, "scalars", fake_scalars)

    result = _get_or_create_workload(db_session, "raced", account_id, max_workloads=0)
    assert result.id == winner.id  # recovered the existing row, no exception raised

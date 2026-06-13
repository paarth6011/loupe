"""The checkin tenant-reset must never raise.

Regression for a production incident: the small prod VM drops DB connections
under memory pressure. When such a dead connection was returned to the pool, the
``checkin`` handler's ``SELECT set_config(...)`` threw, that exception propagated
out of the pool's checkin event and corrupted its accounting, and the slot leaked
— until all of them were gone and every request 500'd with a QueuePool timeout
until the backend was restarted.
"""

from app.database import _reset_tenant_on_checkin


class _DeadCursor:
    def execute(self, *args, **kwargs):
        raise RuntimeError("connection already closed")

    def close(self):
        pass


class _DeadConnection:
    def cursor(self):
        return _DeadCursor()


def test_checkin_reset_swallows_dead_connection_errors():
    # A dead connection makes the reset SQL throw; the handler must absorb it so
    # the pool can still reclaim (and pre_ping later discard) the slot.
    _reset_tenant_on_checkin(_DeadConnection(), connection_record=None)


def test_checkin_reset_clears_the_pin_and_commits_on_a_live_connection():
    executed: list[str] = []
    commits = {"n": 0}

    class _Cursor:
        def execute(self, sql, *args, **kwargs):
            executed.append(sql)

        def close(self):
            pass

    class _LiveConnection:
        def cursor(self):
            return _Cursor()

        def commit(self):
            commits["n"] += 1

    _reset_tenant_on_checkin(_LiveConnection(), connection_record=None)
    assert any("set_config('app.current_account', '', false)" in s for s in executed)
    # Must commit so the connection returns IDLE, not INTRANS — otherwise the next
    # checkout's pool_pre_ping fails ("can't change autocommit ... INTRANS").
    assert commits["n"] == 1

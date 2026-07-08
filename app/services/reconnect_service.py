"""Reconnect handling: rebuild a table_state snapshot for a resuming client from
in-memory/Redis state, rather than replaying every delta.

TODO:
- resume(user, table_id) -> full table_state snapshot, tagged with the current
  monotonic state_version so the client can detect/ignore stale messages
"""

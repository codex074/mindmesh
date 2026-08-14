"""Per-user namespace resolution tests (EXECUTION_PLAN.md D5 / C4)."""

from __future__ import annotations

from pathlib import Path

from app.deep.namespace import (
    DEFAULT_NAMESPACE,
    memory_log_path_for,
    resolve_namespace,
)


def test_resolve_namespace_prefers_auth_header():
    assert resolve_namespace({"X-Authenticated-User": "Alice"}) == "alice"
    assert resolve_namespace({"x-webauth-user": "Bob.Smith"}) == "bob.smith"


def test_resolve_namespace_sanitizes():
    assert resolve_namespace({"X-Authenticated-User": "Alice O'Neil!!"}) == "alice_o_neil"


def test_resolve_namespace_default_when_missing():
    assert resolve_namespace(None) == DEFAULT_NAMESPACE
    assert resolve_namespace({}) == DEFAULT_NAMESPACE


def test_memory_log_path_is_per_user(tmp_path):
    p1 = memory_log_path_for("alice", str(tmp_path))
    p2 = memory_log_path_for("bob", str(tmp_path))
    assert p1 != p2
    assert p1 == tmp_path / "memory" / "alice.md"
    assert p2 == tmp_path / "memory" / "bob.md"
    assert p1.parent.is_dir()
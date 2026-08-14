from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def launcher():
    path = Path(__file__).resolve().parents[1] / "mindmesh"
    loader = importlib.machinery.SourceFileLoader("mindmesh_launcher", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_uses_port_8000_by_default(launcher, monkeypatch, tmp_path):
    monkeypatch.delenv("MINDMESH_PORT", raising=False)
    monkeypatch.setattr(launcher, "PORT_FILE", tmp_path / "port")
    monkeypatch.setattr(launcher, "is_free", lambda port: port == 8000)

    assert launcher.resolve_port() == 8000
    assert (tmp_path / "port").read_text() == "8000"


def test_chooses_free_port_when_8000_is_busy(launcher, monkeypatch, tmp_path):
    monkeypatch.delenv("MINDMESH_PORT", raising=False)
    monkeypatch.setattr(launcher, "PORT_FILE", tmp_path / "port")
    monkeypatch.setattr(launcher, "is_free", lambda port: False)
    monkeypatch.setattr(launcher, "pick_port", lambda: 43123)

    assert launcher.resolve_port() == 43123


def test_prefers_8000_over_an_old_remembered_fallback(launcher, monkeypatch, tmp_path):
    monkeypatch.delenv("MINDMESH_PORT", raising=False)
    port_file = tmp_path / "port"
    port_file.write_text("43123")
    monkeypatch.setattr(launcher, "PORT_FILE", port_file)
    monkeypatch.setattr(launcher, "is_free", lambda port: port in (8000, 43123))

    assert launcher.resolve_port() == 8000


def test_honours_an_available_requested_port(launcher, monkeypatch, tmp_path):
    monkeypatch.setenv("MINDMESH_PORT", "9000")
    monkeypatch.setattr(launcher, "PORT_FILE", tmp_path / "port")
    monkeypatch.setattr(launcher, "is_free", lambda port: port == 9000)

    assert launcher.resolve_port() == 9000


def test_ignores_a_corrupt_remembered_port(launcher, monkeypatch, tmp_path):
    monkeypatch.delenv("MINDMESH_PORT", raising=False)
    port_file = tmp_path / "port"
    port_file.write_text("not-a-port")
    monkeypatch.setattr(launcher, "PORT_FILE", port_file)
    monkeypatch.setattr(launcher, "is_free", lambda port: False)
    monkeypatch.setattr(launcher, "pick_port", lambda: 43123)

    assert launcher.resolve_port() == 43123

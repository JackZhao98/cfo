"""Tests for scheduler registry OS detection."""
import platform

import pytest

from cfo.scheduler import registry


def test_get_backend_mac(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    b = registry.get_backend()
    assert b.__class__.__name__ == "LaunchdBackend"


def test_get_backend_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    b = registry.get_backend()
    assert b.__class__.__name__ == "SystemdBackend"


def test_get_backend_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    b = registry.get_backend()
    assert b.__class__.__name__ == "SchtasksBackend"


def test_get_backend_unknown_raises(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "AIX")
    with pytest.raises(NotImplementedError):
        registry.get_backend()

"""Config.from_env — required vars, mk_ prefix guard, api_base normalization."""

from __future__ import annotations

import pytest
from voqalize_mcp.config import DEFAULT_API_BASE, Config, ConfigError


def _env(monkeypatch, **kv: str) -> None:
    for var in ("VOQALIZE_MANAGEMENT_KEY", "VOQALIZE_TENANT", "VOQALIZE_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    for k, v in kv.items():
        monkeypatch.setenv(k, v)


def test_from_env_happy_path(monkeypatch):
    _env(
        monkeypatch,
        VOQALIZE_MANAGEMENT_KEY="mk_live_abc",
        VOQALIZE_TENANT="acme",
        VOQALIZE_API_BASE="https://cp.example.com/",
    )
    cfg = Config.from_env()
    assert cfg.management_key == "mk_live_abc"
    assert cfg.tenant == "acme"
    assert cfg.api_base == "https://cp.example.com"  # trailing slash stripped


def test_from_env_defaults_api_base(monkeypatch):
    _env(monkeypatch, VOQALIZE_MANAGEMENT_KEY="mk_live_abc", VOQALIZE_TENANT="acme")
    assert Config.from_env().api_base == DEFAULT_API_BASE


def test_from_env_missing_key(monkeypatch):
    _env(monkeypatch, VOQALIZE_TENANT="acme")
    with pytest.raises(ConfigError, match="VOQALIZE_MANAGEMENT_KEY"):
        Config.from_env()


def test_from_env_rejects_non_mk_key(monkeypatch):
    _env(monkeypatch, VOQALIZE_MANAGEMENT_KEY="sk_live_abc", VOQALIZE_TENANT="acme")
    with pytest.raises(ConfigError, match="must be a management key"):
        Config.from_env()


def test_from_env_missing_tenant(monkeypatch):
    _env(monkeypatch, VOQALIZE_MANAGEMENT_KEY="mk_live_abc")
    with pytest.raises(ConfigError, match="VOQALIZE_TENANT"):
        Config.from_env()

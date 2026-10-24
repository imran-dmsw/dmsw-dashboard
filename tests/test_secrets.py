"""Lecture des secrets : clé au premier niveau ou rangée par erreur sous une section TOML."""
import db


def test_secret_premier_niveau(monkeypatch):
    monkeypatch.setattr(db.st, "secrets", {"SUPABASE_URL": "https://a.supabase.co"})
    assert db.secret("SUPABASE_URL") == "https://a.supabase.co"


def test_secret_sous_une_section(monkeypatch):
    monkeypatch.setattr(db.st, "secrets", {"APP_PASSWORD": "x",
                                           "connections": {"supabase": {"SUPABASE_KEY": "k"}}})
    assert db.secret("SUPABASE_KEY") == "k"
    assert db.noms_secrets() == ["APP_PASSWORD", "connections.supabase.SUPABASE_KEY"]


def test_secret_absent(monkeypatch):
    monkeypatch.setattr(db.st, "secrets", {"APP_PASSWORD": "x"})
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert db.secret("SUPABASE_URL") is None

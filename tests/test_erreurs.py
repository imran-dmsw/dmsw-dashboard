"""Erreurs Supabase : message lisible au lieu d'un plantage."""
import pytest
from postgrest.exceptions import APIError

import db


def erreur(code, message):
    return APIError({"code": code, "message": message, "hint": None, "details": None})


@pytest.mark.parametrize("code, message, attendu", [
    ("PGRST205", "Could not find the table 'public.dmsw_parametres' in the schema cache", "n'existe pas"),
    ("42P01", 'relation "dmsw_clients" does not exist', "n'existe pas"),
    ("42703", 'column "updated_at" of relation "dmsw_taches" does not exist', "colonne manque"),
    ("42501", "permission denied for table dmsw_clients", "service_role"),
    ("PGRST301", "JWSError JWSInvalidSignature", "Clé Supabase invalide"),
    ("XX000", "autre chose", "Erreur Supabase (XX000)"),
])
def test_messages(code, message, attendu):
    assert attendu in db.message_erreur(erreur(code, message), "parametres")


class MoteurEnPanne:
    def select(self, table):
        raise erreur("PGRST205", f"Could not find the table 'public.dmsw_{table}' in the schema cache")


def test_lecture_supabase_donne_une_erreur_lisible(monkeypatch):
    monkeypatch.setattr(db, "mode", lambda: "supabase")
    monkeypatch.setattr(db, "get_backend", lambda: MoteurEnPanne())
    db._load.clear()
    with pytest.raises(db.DonneesError, match="dmsw_clients n'existe pas"):
        db.verifier_connexion()
    db._load.clear()

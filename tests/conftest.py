"""Fixtures communes : base SQLite jetable + faux ClickUp en mémoire (aucun appel réseau)."""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clickup_client as cu  # noqa: E402
import db  # noqa: E402
import sync  # noqa: E402


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base SQLite vide, propre à chaque test."""
    monkeypatch.setenv("DMSW_DB_PATH", str(tmp_path / "test.db"))
    db.get_backend.clear()
    db._load.clear()
    yield db
    db.get_backend.clear()
    db._load.clear()


class FauxClickUp:
    """Imite l'API : stocke des tâches normalisées, date_updated avance à chaque écriture."""

    def __init__(self):
        self.taches = {}
        self.n = 0
        self.appels = {"creer": 0, "maj": 0}
        self.decalage = timedelta(0)  # pour simuler une modification « plus tard »

    def maintenant(self):
        return datetime.now() + self.decalage

    def ajouter(self, nom, statut="to do", priorite=None, date_limite=None, ferme=False):
        self.n += 1
        tid = f"cu{self.n}"
        self.taches[tid] = {"id": tid, "nom": nom, "description": "", "statut": statut,
                            "statut_type": "closed" if ferme else "open", "priorite": priorite,
                            "date_limite": date_limite, "date_updated": self.maintenant(),
                            "url": f"https://app.clickup.com/t/{tid}", "tags": []}
        return self.taches[tid]

    def _appliquer(self, t, payload):
        if "name" in payload:
            t["nom"] = payload["name"]
        if "status" in payload:
            t["statut"] = payload["status"]
        if "priority" in payload:
            t["priorite"] = payload["priority"]
        if "due_date" in payload:
            t["date_limite"] = cu.date_depuis_ms(payload["due_date"])
        t["date_updated"] = self.maintenant()
        return dict(t)

    # Remplacent les fonctions de clickup_client
    def taches_liste(self, liste, inclure_fermees=True):
        return [dict(t) for t in self.taches.values()]

    def creer_tache(self, liste, payload):
        self.appels["creer"] += 1
        t = self.ajouter(payload["name"])
        t["tags"] = payload.get("tags", [])
        return self._appliquer(t, payload)

    def maj_tache(self, task_id, payload):
        self.appels["maj"] += 1
        return self._appliquer(self.taches[task_id], payload)


@pytest.fixture
def clickup(monkeypatch):
    faux = FauxClickUp()
    monkeypatch.setattr(cu, "taches_liste", faux.taches_liste)
    monkeypatch.setattr(cu, "creer_tache", faux.creer_tache)
    monkeypatch.setattr(cu, "maj_tache", faux.maj_tache)
    monkeypatch.setattr(cu, "vider_cache", lambda: None)
    monkeypatch.setattr(cu, "list_id", lambda: "liste-test")
    monkeypatch.setattr(cu, "configure", lambda: True)
    return faux


MAPPING = {"a_faire": "to do", "en_cours": "in progress", "valide": "complete"}


def configurer(simulation=False, auto_envoi=False, importer=True, mapping=MAPPING):
    db.set_reglages({sync.R_SIMULATION: "1" if simulation else "0",
                     sync.R_AUTO_ENVOI: "1" if auto_envoi else "0",
                     sync.R_IMPORT: "1" if importer else "0"})
    if mapping:
        db.set_reglages({sync.R_MAP[k]: v for k, v in mapping.items()})

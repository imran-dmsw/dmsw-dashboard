"""Appels à l'API ClickUp (v2) : lecture des tâches et statuts, création, mise à jour.

- Le token est lu dans st.secrets (CLICKUP_TOKEN) et n'est jamais affiché ni journalisé.
- Chaque appel a un timeout de 15 s ; une réponse 429 (trop de requêtes) est
  réessayée après une pause ; les erreurs deviennent des ClickUpError en français.
- Les lectures sont mises en cache 5 minutes (st.cache_data) pour ménager la limite
  d'environ 100 requêtes par minute.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import requests
import streamlit as st

import db

API = "https://api.clickup.com/api/v2"
TIMEOUT = 15
ESSAIS_429 = 3
MAX_PAGES = 20
try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover - zoneinfo absent (très vieux Python)
    PARIS = None


class ClickUpError(Exception):
    """Erreur lisible, à afficher telle quelle à l'utilisateur."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _token():
    return db.secret("CLICKUP_TOKEN")


def list_id():
    return str(db.secret("CLICKUP_LIST_ID", "") or "")


def configure() -> bool:
    """Vrai si le token et l'identifiant de liste sont présents."""
    return bool(_token()) and bool(list_id())


# ---------------------------------------------------------------------------
# Conversions de dates (ClickUp = timestamps en millisecondes)
# ---------------------------------------------------------------------------
def date_depuis_ms(ms) -> date | None:
    """Échéance ClickUp (ms) -> date au fuseau Europe/Paris. None si aucune date."""
    if ms in (None, "", 0, "0"):
        return None
    dt = datetime.fromtimestamp(int(ms) / 1000, tz=PARIS)
    return dt.date()


def date_vers_ms(d: date | None):
    """Date locale -> timestamp ClickUp (ms), à midi heure de Paris pour éviter
    tout décalage de jour. None si aucune date."""
    if not d:
        return None
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=PARIS)
    return int(dt.timestamp() * 1000)


def dt_depuis_ms(ms) -> datetime | None:
    """Horodatage ClickUp (ms) -> datetime locale sans fuseau (comme updated_at)."""
    if ms in (None, "", 0, "0"):
        return None
    return datetime.fromtimestamp(int(ms) / 1000)


def normaliser(t: dict) -> dict:
    """Réponse brute d'une tâche ClickUp -> dictionnaire simple utilisé partout."""
    statut = t.get("status") or {}
    prio = t.get("priority") or {}
    return {
        "id": str(t.get("id")),
        "nom": t.get("name") or "",
        "description": t.get("text_content") or t.get("description") or "",
        "statut": (statut.get("status") or "").lower(),
        "statut_type": statut.get("type") or "",
        "priorite": int(prio["id"]) if prio and prio.get("id") else None,
        "date_limite": date_depuis_ms(t.get("due_date")),
        "date_updated": dt_depuis_ms(t.get("date_updated")),
        "url": t.get("url") or "",
        "tags": [g.get("name") for g in t.get("tags") or []],
    }


# ---------------------------------------------------------------------------
# Requêtes HTTP
# ---------------------------------------------------------------------------
def _requete(methode: str, chemin: str, params=None, json=None) -> dict:
    token = _token()
    if not token:
        raise ClickUpError("Intégration ClickUp non configurée (CLICKUP_TOKEN absent).")
    entetes = {"Authorization": str(token), "Content-Type": "application/json"}
    for essai in range(ESSAIS_429 + 1):
        try:
            r = requests.request(methode, API + chemin, headers=entetes, params=params,
                                 json=json, timeout=TIMEOUT)
        except requests.Timeout:
            raise ClickUpError("ClickUp ne répond pas (délai de 15 s dépassé). Réessaie plus tard.") from None
        except requests.RequestException:
            raise ClickUpError("Impossible de joindre ClickUp : connexion internet coupée ?") from None

        if r.status_code == 429 and essai < ESSAIS_429:
            # Pause jusqu'à la remise à zéro du quota (bornée à 10 s)
            reset = r.headers.get("X-RateLimit-Reset")
            pause = 3.0
            if reset and reset.isdigit():
                pause = min(max(int(reset) - time.time(), 1), 10)
            time.sleep(pause)
            continue
        if r.status_code == 429:
            raise ClickUpError("Trop de requêtes vers ClickUp (limite atteinte). Réessaie dans une minute.")
        if r.status_code == 401:
            raise ClickUpError("Token ClickUp invalide ou expiré (401). Vérifie CLICKUP_TOKEN dans les secrets.")
        if r.status_code == 404:
            raise ClickUpError("Élément introuvable dans ClickUp (404). Vérifie CLICKUP_LIST_ID.")
        if r.status_code >= 400:
            try:
                detail = r.json().get("err") or ""
            except ValueError:
                detail = ""
            raise ClickUpError(f"Erreur ClickUp {r.status_code}. {detail}".strip())
        try:
            return r.json() if r.content else {}
        except ValueError:
            raise ClickUpError("Réponse ClickUp illisible.") from None
    raise ClickUpError("Erreur ClickUp inattendue.")  # pragma: no cover


# ---------------------------------------------------------------------------
# Lectures (en cache 5 minutes)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Lecture de ClickUp…")
def taches_liste(liste: str, inclure_fermees: bool = True) -> list:
    """Toutes les tâches de la liste, page par page (100 par page)."""
    out = []
    for page in range(MAX_PAGES):
        data = _requete("GET", f"/list/{liste}/task", params={
            "page": page, "include_closed": str(inclure_fermees).lower(), "subtasks": "true"})
        lot = data.get("tasks") or []
        out.extend(normaliser(t) for t in lot)
        if data.get("last_page", True) or not lot:
            break
    return out


@st.cache_data(ttl=300, show_spinner=False)
def statuts_liste(liste: str) -> list:
    """Statuts réels de la liste, dans l'ordre ClickUp : [{'nom', 'type'}]."""
    data = _requete("GET", f"/list/{liste}")
    return [{"nom": (s.get("status") or "").lower(), "type": s.get("type") or ""}
            for s in data.get("statuses") or []]


def vider_cache():
    taches_liste.clear()
    statuts_liste.clear()


# ---------------------------------------------------------------------------
# Écritures
# ---------------------------------------------------------------------------
def creer_tache(liste: str, payload: dict) -> dict:
    return normaliser(_requete("POST", f"/list/{liste}/task", json=payload))


def maj_tache(task_id: str, payload: dict) -> dict:
    return normaliser(_requete("PUT", f"/task/{task_id}", json=payload))


def aujourd_hui_paris() -> date:
    return datetime.now(PARIS).date() if PARIS else date.today()


def en_retard(t: dict, ref: date | None = None) -> bool:
    ref = ref or aujourd_hui_paris()
    return bool(t["date_limite"] and t["date_limite"] < ref and t["statut_type"] != "closed")


def due_bientot(t: dict, jours: int = 0, ref: date | None = None) -> bool:
    ref = ref or aujourd_hui_paris()
    return bool(t["date_limite"] and t["statut_type"] != "closed"
                and t["date_limite"] <= ref + timedelta(days=jours))

"""Lecture des DM Instagram via l'API officielle de Meta (« Instagram API with Instagram Login »).

- Lecture seule : l'app ne publie et n'envoie jamais rien sur Instagram.
- Jeton : INSTAGRAM_TOKEN dans st.secrets (jeton longue durée, 60 jours). Une fois renouvelé
  depuis l'app, le nouveau jeton est gardé dans la table parametres (jamais affiché).
- Limites Meta : 2 appels par seconde et par compte ; seuls les 20 derniers messages d'une
  conversation sont lisibles ; les « demandes » inactives depuis 30 jours ne sont pas renvoyées.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import requests

import db

API = "https://graph.instagram.com/v27.0"
REFRESH = "https://graph.instagram.com/refresh_access_token"
TIMEOUT = 15
PAUSE = 0.55  # secondes entre deux appels (limite Meta : 2 par seconde)
R_TOKEN = "instagram_token"            # jeton renouvelé (table parametres)
R_TOKEN_DATE = "instagram_token_date"  # date du dernier renouvellement (ISO)
R_EXPIRE = "instagram_token_expire"    # date d'expiration estimée (ISO)

_dernier_appel = [0.0]


class InstagramError(Exception):
    """Erreur lisible, à afficher telle quelle."""


def _token():
    return db.reglage(R_TOKEN) or db.secret("INSTAGRAM_TOKEN")


def configure() -> bool:
    return bool(_token())


def _attendre():
    reste = PAUSE - (time.time() - _dernier_appel[0])
    if reste > 0:
        time.sleep(reste)
    _dernier_appel[0] = time.time()


def _get(url: str, params: dict | None = None) -> dict:
    """GET avec jeton, pause anti-limite et erreurs en français (jamais le jeton)."""
    token = _token()
    if not token:
        raise InstagramError("Instagram non configuré (INSTAGRAM_TOKEN absent).")
    params = dict(params or {})
    if "access_token=" not in url:
        params["access_token"] = token
    _attendre()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.Timeout:
        raise InstagramError("Instagram ne répond pas (délai de 15 s dépassé).") from None
    except requests.RequestException:
        raise InstagramError("Impossible de joindre Instagram : connexion internet coupée ?") from None
    try:
        data = r.json()
    except ValueError:
        raise InstagramError(f"Réponse Instagram illisible ({r.status_code}).") from None
    if r.status_code >= 400 or "error" in data:
        err = data.get("error") or {}
        code = err.get("code")
        if code == 190 or r.status_code == 401:
            raise InstagramError("Jeton Instagram invalide ou expiré : génère un nouveau jeton "
                                 "(voir le README) et mets-le dans INSTAGRAM_TOKEN.")
        if code in (4, 17, 32, 613) or r.status_code == 429:
            raise InstagramError("Trop de requêtes vers Instagram : réessaie dans quelques minutes.")
        if code in (10, 200) or (isinstance(code, int) and 200 <= code < 300):
            raise InstagramError("Autorisation manquante : le jeton doit inclure "
                                 "instagram_business_basic et instagram_business_manage_messages.")
        raise InstagramError(f"Erreur Instagram {code or r.status_code} : {str(err.get('message', ''))[:150]}")
    return data


def moi() -> dict:
    """Compte connecté : {'id', 'username'}."""
    data = _get(f"{API}/me", {"fields": "user_id,username"})
    return {"id": str(data.get("user_id") or data.get("id") or ""), "username": data.get("username") or ""}


def conversations(maximum: int = 100) -> list:
    """Conversations, de la plus récente à la plus ancienne : [{'id', 'updated_time'}]."""
    out = []
    data = _get(f"{API}/me/conversations", {"platform": "instagram", "fields": "id,updated_time"})
    while True:
        for c in data.get("data") or []:
            out.append({"id": str(c["id"]), "updated_time": _date(c.get("updated_time"))})
            if len(out) >= maximum:
                return out
        suivant = (data.get("paging") or {}).get("next")
        if not suivant:
            return out
        data = _get(suivant)


def dernier_message(conversation_id: str) -> dict | None:
    """Dernier message d'une conversation : {'de_id', 'de_username', 'a_id', 'a_username',
    'texte', 'date'} ; None si la conversation est vide."""
    data = _get(f"{API}/{conversation_id}", {"fields": "messages"})
    messages = ((data.get("messages") or {}).get("data")) or []
    if not messages:
        return None
    recent = max(messages, key=lambda m: m.get("created_time") or "")
    m = _get(f"{API}/{recent['id']}", {"fields": "id,created_time,from,to,message"})
    de = m.get("from") or {}
    a = ((m.get("to") or {}).get("data") or [{}])[0]
    return {"de_id": str(de.get("id") or ""), "de_username": de.get("username") or "",
            "a_id": str(a.get("id") or ""), "a_username": a.get("username") or "",
            "texte": m.get("message") or "", "date": _date(m.get("created_time"))}


def rafraichir_token() -> datetime:
    """Renouvelle le jeton (60 jours de plus) et le garde en base. Renvoie la nouvelle expiration."""
    data = _get(REFRESH, {"grant_type": "ig_refresh_token"})
    nouveau = data.get("access_token")
    if not nouveau:
        raise InstagramError("Instagram n'a pas renvoyé de nouveau jeton.")
    expire = datetime.now() + timedelta(seconds=int(data.get("expires_in") or 60 * 86400))
    db.set_reglages({R_TOKEN: nouveau, R_TOKEN_DATE: datetime.now().isoformat(timespec="seconds"),
                     R_EXPIRE: expire.isoformat(timespec="seconds")})
    return expire


def expiration():
    v = db.reglage(R_EXPIRE)
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def _date(v):
    """« 2026-11-10T14:03:00+0000 » -> datetime locale sans fuseau."""
    if not v:
        return None
    try:
        from dateutil import parser
        dt = parser.isoparse(str(v))
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt

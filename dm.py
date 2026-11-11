"""Suivi des DM : prospects Instagram (importés automatiquement) et TikTok (saisis à la main).

L'import Instagram ne fait que lire : il crée un prospect par nouvelle conversation et
met à jour la date et l'auteur du dernier message. Le statut reste géré à la main.
Rejouer l'import ne crée aucun doublon (une conversation = un prospect).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import db
import instagram_client as ig

PLATEFORMES = {"instagram": "Instagram", "tiktok": "TikTok", "autre": "Autre"}
ICONES = {"instagram": "📸", "tiktok": "🎵", "autre": "💬"}
STATUTS = {"nouveau": "Nouveau", "en_discussion": "En discussion", "relance": "Relancé",
           "rdv": "Rendez-vous", "devis": "Devis envoyé", "converti": "Converti en client",
           "perdu": "Perdu"}
FERMES = ("converti", "perdu")
APERCU_MAX = 120
DELAI_RELANCE = 3  # jours, bouton « Relancé »
INTERVALLE_AUTO = timedelta(minutes=15)
R_DERNIER_IMPORT = "instagram_dernier_import"
R_MOI = "instagram_moi"  # nom d'utilisateur du compte, pour savoir qui a écrit en dernier
R_IGNORES = "instagram_ignores"  # conversations retirées du suivi : jamais réimportées


def profil_url(plateforme: str, pseudo: str) -> str:
    pseudo = (pseudo or "").strip().lstrip("@")
    if not pseudo:
        return ""
    if plateforme == "instagram":
        return f"https://www.instagram.com/{pseudo}/"
    if plateforme == "tiktok":
        return f"https://www.tiktok.com/@{pseudo}"
    return ""


def a_repondre(p: dict) -> bool:
    """La personne a écrit en dernier et le dossier n'est pas clos."""
    return p["dernier_message_de"] == "eux" and p["statut"] not in FERMES


def relance_due(p: dict, aujourd_hui: date | None = None) -> bool:
    aujourd_hui = aujourd_hui or date.today()
    return bool(p["prochaine_relance"] and p["prochaine_relance"] <= aujourd_hui and p["statut"] not in FERMES)


def a_traiter(p: dict, aujourd_hui: date | None = None) -> bool:
    return a_repondre(p) or relance_due(p, aujourd_hui)


def marquer_relance(p: dict):
    db.update_prospect(p["id"], {"statut": "relance", "dernier_message_de": "moi",
                                 "prochaine_relance": date.today() + timedelta(days=DELAI_RELANCE)})


def convertir_en_client(p: dict) -> int:
    """Crée la fiche client (statut prospect) et relie le prospect. Renvoie l'id du client."""
    if p["client_lie_id"] and db.client(p["client_lie_id"]):
        return p["client_lie_id"]
    nom = (p["nom"] or "").strip() or f"@{(p['pseudo'] or '').lstrip('@')}"
    source = f"Prospect venu de {PLATEFORMES.get(p['plateforme'], p['plateforme'])}"
    if p["pseudo"]:
        source += f" (@{p['pseudo'].lstrip('@')})"
    cid = db.create_client({"nom": nom, "activite": p["secteur"] or "", "statut_projet": "prospect",
                            "notes": f"{source}. {p['notes'] or ''}".strip()})
    db.update_prospect(p["id"], {"client_lie_id": cid, "statut": "converti"})
    db.add_historique(cid, "note", f"{source} : converti depuis le suivi des DM.")
    return cid


def ignores() -> set:
    return {x for x in db.reglage(R_IGNORES).split(",") if x}


def supprimer(p: dict):
    """Retire un prospect du suivi ; une conversation Instagram supprimée n'est plus réimportée."""
    if p["ig_conversation_id"]:
        db.set_reglages({R_IGNORES: ",".join(sorted(ignores() | {p["ig_conversation_id"]}))})
    db.delete_prospect(p["id"])


def _apercu(texte: str) -> str:
    texte = " ".join((texte or "").split())
    return texte if len(texte) <= APERCU_MAX else texte[:APERCU_MAX - 1] + "…"


# ---------------------------------------------------------------------------
# Import Instagram
# ---------------------------------------------------------------------------
def importer_instagram(maximum: int = 100, progression=None) -> dict:
    """Lit les conversations Instagram et met le suivi à jour.
    Seules les conversations nouvelles ou modifiées depuis le dernier passage sont détaillées
    (2 appels chacune), pour rester sous la limite de Meta.
    progression(i, n) : appelée pendant la lecture (barre de progression)."""
    stats = {"crees": 0, "mis_a_jour": 0, "inchanges": 0, "vides": 0}
    moi_nom = db.reglage(R_MOI)
    if not moi_nom:
        moi_nom = ig.moi()["username"]
        db.set_reglages({R_MOI: moi_nom})
    connus = {p["ig_conversation_id"]: p for p in db.prospects() if p["ig_conversation_id"]}
    ecartees = ignores()
    convs = [c for c in ig.conversations(maximum) if c["id"] not in ecartees]
    for i, c in enumerate(convs):
        if progression:
            progression(i, len(convs))
        p = connus.get(c["id"])
        if p and p["dernier_message_le"] and c["updated_time"] and c["updated_time"] <= p["dernier_message_le"]:
            stats["inchanges"] += 1
            continue
        m = ig.dernier_message(c["id"])
        if not m:
            stats["vides"] += 1
            continue
        de_moi = m["de_username"].lower() == moi_nom.lower() if moi_nom else False
        autre_nom = m["a_username"] if de_moi else m["de_username"]
        autre_id = m["a_id"] if de_moi else m["de_id"]
        data = {"dernier_message_le": m["date"] or c["updated_time"],
                "dernier_message_de": "moi" if de_moi else "eux", "apercu": _apercu(m["texte"])}
        if p:
            db.update_prospect(p["id"], data)
            stats["mis_a_jour"] += 1
        else:
            db.create_prospect({**data, "plateforme": "instagram", "pseudo": autre_nom,
                                "profil_url": profil_url("instagram", autre_nom),
                                "ig_conversation_id": c["id"], "ig_user_id": autre_id})
            stats["crees"] += 1
    db.set_reglages({R_DERNIER_IMPORT: datetime.now().isoformat(timespec="seconds")})
    return stats


def dernier_import():
    v = db.reglage(R_DERNIER_IMPORT)
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def import_auto():
    """Au chargement de l'app : import si configuré et si le dernier date de plus de 15 minutes.
    Renouvelle aussi le jeton chaque semaine. Ne lève jamais d'erreur."""
    if not ig.configure():
        return
    dernier = dernier_import()
    if dernier is None or datetime.now() - dernier < INTERVALLE_AUTO:
        return  # le tout premier import se lance à la main (il peut être long)
    try:
        renouvele = db.reglage(ig.R_TOKEN_DATE)
        if not renouvele or datetime.now() - datetime.fromisoformat(renouvele) > timedelta(days=7):
            ig.rafraichir_token()
    except (ig.InstagramError, ValueError):
        pass  # ex. jeton de moins de 24 h : Meta refuse, on réessaiera plus tard
    try:
        importer_instagram(maximum=50)
    except ig.InstagramError:
        db.set_reglages({R_DERNIER_IMPORT: datetime.now().isoformat(timespec="seconds")})

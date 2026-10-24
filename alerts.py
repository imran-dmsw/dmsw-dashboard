"""Règles d'alertes automatiques.

Les alertes sont recalculées à chaque chargement à partir des fiches clients :
rien n'est stocké. Chaque alerte a une catégorie (qui alimente un voyant),
un niveau (orange / rouge) et un message lisible.
"""
from __future__ import annotations

from datetime import date

import db

# Catégories = colonnes de voyants de la vue d'ensemble
CATEGORIES = {
    "paiement": "Paiement",
    "echeances": "Domaine / hébergement",
    "seo": "SEO",
    "suivi": "Suivi",
}
NIVEAUX = {"ok": 0, "orange": 1, "rouge": 2}

EN_LIGNE = ("livre", "maintenance")           # site livré / en ligne
SUIVIS = ("en_cours", "livre", "maintenance")  # projets actifs


def _alerte(c, categorie, niveau, message):
    return {"client_id": c["id"], "client_nom": c["nom"], "categorie": categorie,
            "niveau": niveau, "message": message}


def alertes_client(c: dict, p: dict, today: date | None = None) -> list:
    """Toutes les alertes d'un client, selon les seuils `p` (db.parametres())."""
    today = today or date.today()
    statut = c["statut_projet"]
    if statut == "archive" or c.get("interne"):
        return []  # client archivé ou « DMSW (interne) » : jamais d'alerte
    out = []

    # --- Paiement ---------------------------------------------------------
    if not c["paiement_a_jour"]:
        out.append(_alerte(c, "paiement", "rouge", "Paiement marqué « pas à jour »."))
    dpp = c["date_prochain_paiement"]
    if dpp and dpp < today:
        out.append(_alerte(c, "paiement", "rouge",
                           f"Paiement attendu le {dpp:%d/%m/%Y} : en retard de {(today - dpp).days} j."))
    livraison = c["date_livraison"]
    if (c["solde_restant"] > 0 and statut in EN_LIGNE and livraison
            and (today - livraison).days > p["solde_jours_apres_livraison"]):
        out.append(_alerte(c, "paiement", "rouge",
                           f"Solde de {db.fmt_euro(c['solde_restant'])} non réglé, "
                           f"site livré il y a {(today - livraison).days} j."))
    if statut == "maintenance" and c["abonnement_mensuel"] <= 0:
        out.append(_alerte(c, "paiement", "orange",
                           "Client en maintenance sans abonnement enregistré."))

    # --- Domaine / hébergement -------------------------------------------
    for champ, libelle in (("date_renouvellement_domaine", "domaine"),
                           ("date_renouvellement_hebergement", "hébergement")):
        d = c[champ]
        if not d:
            continue
        jours = (d - today).days
        if jours < 0:
            out.append(_alerte(c, "echeances", "rouge",
                               f"Renouvellement {libelle} dépassé depuis {-jours} j ({d:%d/%m/%Y})."))
        elif jours < p["renouvellement_rouge_jours"]:
            out.append(_alerte(c, "echeances", "rouge",
                               f"Renouvellement {libelle} dans {jours} j ({d:%d/%m/%Y})."))
        elif jours < p["renouvellement_orange_jours"]:
            out.append(_alerte(c, "echeances", "orange",
                               f"Renouvellement {libelle} dans {jours} j ({d:%d/%m/%Y})."))

    # --- SEO (sites en ligne) --------------------------------------------
    if statut in EN_LIGNE:
        audit = c["date_dernier_audit_seo"]
        if not audit:
            out.append(_alerte(c, "seo", "orange", "Aucun audit SEO enregistré."))
        elif (today - audit).days > p["audit_seo_jours"]:
            out.append(_alerte(c, "seo", "orange",
                               f"Dernier audit SEO il y a {(today - audit).days} j."))
        if c["seo_statut"] == "a_faire":
            out.append(_alerte(c, "seo", "orange", "SEO encore « à faire » sur un site livré."))

    # --- Suivi : corrections ---------------------------------------------
    incl, util = c["corrections_incluses"] or 0, c["corrections_utilisees"] or 0
    if (incl > 0 or util > 0) and util >= incl:
        out.append(_alerte(c, "suivi", "orange",
                           f"Corrections utilisées {util}/{incl} : la suite est facturée "
                           f"{p['tarif_horaire']} €/h."))
    return out


def toutes_alertes(clients: list, p: dict, today: date | None = None) -> list:
    out = []
    for c in clients:
        out.extend(alertes_client(c, p, today))
    # Rouge d'abord
    return sorted(out, key=lambda a: -NIVEAUX[a["niveau"]])


def voyant(alertes: list, categorie: str | None = None) -> str:
    """Pire niveau des alertes (d'une catégorie) : 'ok', 'orange' ou 'rouge'."""
    niveaux = [a["niveau"] for a in alertes if categorie is None or a["categorie"] == categorie]
    return max(niveaux, key=NIVEAUX.get, default="ok")

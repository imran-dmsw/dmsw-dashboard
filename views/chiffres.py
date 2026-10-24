"""📈 Tableau de bord : les chiffres de l'agence (argent, abonnements, prospects, tâches)."""
from datetime import date

import streamlit as st

import alerts
import db
import ui

ui.entete("Chiffres", "Tableau de bord",
          "Les chiffres clés de l'agence : ce qui est signé, encaissé, récurrent et ce qui reste à faire.")

today = date.today()
debut_mois = today.replace(day=1)
# Clients réels uniquement : ni archivés ni « DMSW (interne) »
tous = [c for c in db.clients() if not c["interne"]]
clients = [c for c in tous if c["statut_projet"] != "archive"]
signes = [c for c in clients if c["statut_projet"] in alerts.SUIVIS]
prospects = [c for c in clients if c["statut_projet"] == "prospect"]
ids = {c["id"] for c in clients}
taches = [t for t in db.taches() if t["client_id"] in ids]

if not tous:
    st.info("Aucun client pour l'instant : les chiffres apparaîtront dès la première fiche.")
    st.stop()

# --- Argent ------------------------------------------------------------------------
ca_signe = sum(c["prix_site"] for c in signes)
encaisse = sum(c["acompte_recu"] for c in signes)
reste = sum(max(c["solde_restant"], 0) for c in signes)
mrr = sum(c["abonnement_mensuel"] for c in clients)
abonnes = [c for c in clients if c["abonnement_mensuel"] > 0]
payants = [c for c in signes if c["prix_site"] > 0]

st.markdown("### Argent")
ui.kpis([
    ("Chiffre d'affaires signé (sites)", db.fmt_euro(ca_signe), "accent"),
    ("Déjà encaissé", db.fmt_euro(encaisse), ""),
    ("Reste à encaisser", db.fmt_euro(reste), "rouge" if reste else ""),
    ("Revenu mensuel récurrent", db.fmt_euro(mrr), "accent"),
    ("Projection annuelle des abonnements", db.fmt_euro(mrr * 12), ""),
    ("Prix moyen d'un site", db.fmt_euro(ca_signe / len(payants)) if payants else "—", ""),
])

g, d = st.columns(2)
with g:
    ui.carte_barres("Chiffre d'affaires par client", sorted(
        [(c["nom"], round(c["prix_site"]), ui.BLEU) for c in signes if c["prix_site"] > 0],
        key=lambda x: -x[1])[:8] or [("Aucun prix renseigné", 0, ui.BLEU)], formateur=db.fmt_euro)
with d:
    ui.carte_barres("Abonnements mensuels", sorted(
        [(c["nom"], round(c["abonnement_mensuel"], 2), ui.BLEU) for c in abonnes],
        key=lambda x: -x[1])[:8] or [("Aucun abonnement", 0, ui.BLEU)], formateur=db.fmt_euro)

# --- Clients -------------------------------------------------------------------------
st.markdown("### Clients")
en_maintenance = [c for c in clients if c["statut_projet"] == "maintenance"]
livres = [c for c in clients if c["statut_projet"] in ("livre", "maintenance")]
ui.kpis([
    ("Clients signés", len(signes), "accent"),
    ("Prospects en cours", len(prospects), ""),
    ("Valeur des prospects (prix renseignés)", db.fmt_euro(sum(c["prix_site"] for c in prospects)), ""),
    ("Sites livrés", len(livres), ""),
    ("Abonnés", f"{len(abonnes)} / {len(livres)} livrés" if livres else str(len(abonnes)), ""),
    ("Clients archivés", sum(c["statut_projet"] == "archive" for c in tous), ""),
])
ui.carte_barres("Clients par statut", [
    (lbl, sum(c["statut_projet"] == s for c in tous), ui.BLEU) for s, lbl in db.STATUTS_PROJET.items()])

# --- Tâches ---------------------------------------------------------------------------
st.markdown("### Tâches")
ouvertes = [t for t in taches if t["statut"] != "valide"]
validees = [t for t in taches if t["statut"] == "valide"]
retard = [t for t in ouvertes if t["date_limite"] and t["date_limite"] < today]
ce_mois = [t for t in validees if t["date_validation"] and t["date_validation"] >= debut_mois]
ui.kpis([
    ("Tâches ouvertes", len(ouvertes), "accent"),
    ("En retard", len(retard), "rouge" if retard else ""),
    ("Validées ce mois-ci", len(ce_mois), ""),
    ("Taux d'avancement", f"{round(100 * len(validees) / len(taches))} %" if taches else "—", ""),
    ("Validées par le client", sum(t["valide_par"] == "client" for t in validees), ""),
    ("Urgentes ouvertes", sum(t["priorite"] == "urgente" for t in ouvertes),
     "rouge" if any(t["priorite"] == "urgente" for t in ouvertes) else ""),
])
noms = {c["id"]: c["nom"] for c in clients}
par_client = {}
for t in ouvertes:
    par_client[t["client_id"]] = par_client.get(t["client_id"], 0) + 1
ui.carte_barres("Tâches ouvertes par client", sorted(
    [(noms[cid], n, ui.ROUGE if any(t["client_id"] == cid for t in retard) else ui.BLEU)
     for cid, n in par_client.items()], key=lambda x: -x[1])[:10] or [("Aucune tâche ouverte", 0, ui.BLEU)])
st.caption("Le client « DMSW (interne) » et les clients archivés sont exclus des chiffres "
           "(sauf le compteur d'archivés).")

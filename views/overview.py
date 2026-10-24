"""📊 Vue d'ensemble : indicateurs, tableau global des clients, filtres."""
from datetime import date

import pandas as pd
import streamlit as st

import alerts
import db
import ui

ui.entete("Pilotage", "Vue d'ensemble",
          "Tous tes clients d'un coup d'œil : argent, échéances, SEO et sécurité.")

today = date.today()
p = db.parametres()
clients = db.clients()
taches = db.taches()

if not clients:
    st.info("Aucun client pour l'instant. Crée ta première fiche, ou charge les données de "
            "démo dans ⚙️ Paramètres.")
    if st.button("➕ Nouveau client", type="primary"):
        st.session_state["edit_mode"] = "nouveau"
        st.switch_page("views/edit_client.py")
    st.stop()

# --- Indicateurs -------------------------------------------------------------
# Le client « DMSW (interne) » est exclu des totaux (revenus, solde, clients actifs)
non_archives = [c for c in clients if c["statut_projet"] != "archive" and not c["interne"]]
actifs = [c for c in non_archives if c["statut_projet"] in alerts.SUIVIS]
toutes = alerts.toutes_alertes(non_archives, p, today)
ids_archives = {c["id"] for c in clients if c["statut_projet"] == "archive"}
en_retard = [t for t in taches if t["statut"] != "valide" and t["date_limite"]
             and t["date_limite"] < today and t["client_id"] not in ids_archives]

horizon = p["taches_horizon_jours"]
a_venir = [t for t in taches if t["statut"] != "valide" and t["date_limite"]
           and 0 <= (t["date_limite"] - today).days <= horizon and t["client_id"] not in ids_archives]
rouges = [a for a in toutes if a["niveau"] == "rouge"]

ui.indicateur_sprint()

# Bandeau d'état
if rouges:
    nb_clients = len({a["client_id"] for a in rouges})
    ui.bandeau("rouge", f"{len(rouges)} alerte(s) urgente(s) sur {nb_clients} client(s) "
                        f"et {len(en_retard)} tâche(s) en retard : commence par la page Aujourd'hui.")
elif toutes or en_retard:
    ui.bandeau("orange", f"{len(toutes)} point(s) à surveiller, rien d'urgent.")
else:
    ui.bandeau("ok", "Tout est à jour : aucun retard, aucune alerte.")

ui.kpis([
    ("Clients actifs", len(actifs), "accent"),
    ("Revenu mensuel récurrent", db.fmt_euro(sum(c["abonnement_mensuel"] for c in non_archives)), ""),
    ("Solde à encaisser", db.fmt_euro(sum(max(c["solde_restant"], 0) for c in non_archives)), ""),
    ("Tâches en retard", len(en_retard), "rouge" if en_retard else ""),
    (f"Tâches à {horizon} jours", len(a_venir), ""),
    ("Alertes", len(toutes), "rouge" if rouges else ""),
])

# Cartes à barres : alertes par rubrique, clients par statut
g, d = st.columns(2)
with g:
    ui.carte_barres("Alertes par rubrique", [
        (lbl, sum(a["categorie"] == cat for a in toutes),
         ui.ROUGE if any(a["categorie"] == cat for a in rouges) else ui.BLEU)
        for cat, lbl in alerts.CATEGORIES.items()
    ])
with d:
    ui.carte_barres("Clients par statut", [
        (lbl, sum(c["statut_projet"] == s for c in clients), ui.BLEU)
        for s, lbl in db.STATUTS_PROJET.items()
    ])

# --- Filtres -----------------------------------------------------------------
f1, f2, f3 = st.columns([2, 2, 1.3], vertical_alignment="bottom")
statuts = f1.multiselect(
    "Statut projet", list(db.STATUTS_PROJET), format_func=db.STATUTS_PROJET.get,
    default=[s for s in db.STATUTS_PROJET if s != "archive"],
)
recherche = f2.text_input("Rechercher un client", placeholder="Nom…")
rouge_seul = f3.toggle("🔴 Rouge uniquement")

# --- Tableau -----------------------------------------------------------------
lignes = []
for c in clients:
    if c["statut_projet"] not in statuts:
        continue
    if recherche and recherche.lower() not in (c["nom"] or "").lower():
        continue
    al = alerts.alertes_client(c, p, today)
    if rouge_seul and alerts.voyant(al) != "rouge":
        continue
    action = ui.prochaine_action([t for t in taches if t["client_id"] == c["id"]])
    v = {cat: ui.EMOJI_VOYANT[alerts.voyant(al, cat)] for cat in alerts.CATEGORIES}
    lignes.append({
        "id": c["id"],
        "Client": c["nom"],
        "Statut": db.STATUTS_PROJET.get(c["statut_projet"], c["statut_projet"]),
        "Paiement": v["paiement"],
        "Prochain paiement": c["date_prochain_paiement"],
        "Domaine / héb.": v["echeances"],
        "SEO": v["seo"],
        "Sécurité": v["securite"],
        "Prochaine action": action["titre"] if action else "—",
        "Date limite": action["date_limite"] if action else None,
    })

if not lignes:
    st.info("Aucun client ne correspond aux filtres.")
    st.stop()

df = pd.DataFrame(lignes)
for col in ("Prochain paiement", "Date limite"):  # « — » au lieu de « None »
    df[col] = df[col].map(ui.fmt_date)
st.caption("Clique sur une ligne pour ouvrir la fiche du client.")
event = st.dataframe(
    df.drop(columns="id"),
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="overview_table",
    column_config={
        "Paiement": st.column_config.TextColumn(width="small"),
        "Domaine / héb.": st.column_config.TextColumn(width="small"),
        "SEO": st.column_config.TextColumn(width="small"),
        "Sécurité": st.column_config.TextColumn(width="small"),
    },
)
st.caption("🟢 OK · 🟠 à surveiller · 🔴 urgent ou en retard")

if event.selection.rows:
    st.session_state["client_id"] = int(df.iloc[event.selection.rows[0]]["id"])
    st.switch_page("views/client.py")

# Sélecteur de secours (pratique sur mobile)
with st.expander("Ouvrir une fiche client"):
    noms = dict(zip(df["id"], df["Client"]))
    choix = st.selectbox("Client", list(noms), format_func=noms.get, key="overview_open")
    if st.button("Ouvrir la fiche", type="primary"):
        st.session_state["client_id"] = int(choix)
        st.switch_page("views/client.py")

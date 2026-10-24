"""📅 Calendrier des échéances : 90 prochains jours, groupés par semaine."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from dateutil.relativedelta import relativedelta

import db
import ui

JOURS = 90
today = date.today()
fin = today + timedelta(days=JOURS)
ui.entete("Échéances", "Calendrier",
          f"Paiements, renouvellements et tâches du {today:%d/%m/%Y} au {fin:%d/%m/%Y}.")

# Un seul accent : nuances du bleu DMSW
COULEURS = {"Paiement": ui.BLEU, "Domaine": "#6db3ea", "Hébergement": "#b5d7f4", "Tâche": ui.BLEU_FONCE}

clients = {c["id"]: c for c in db.clients() if c["statut_projet"] != "archive"}
events = []
for c in clients.values():
    # Paiements d'abonnement : la prochaine date puis une par mois
    d = c["date_prochain_paiement"]
    if c["abonnement_mensuel"] > 0 and d:
        n = 0
        while d + relativedelta(months=n) <= fin:
            jour = d + relativedelta(months=n)
            if jour >= today:
                events.append((jour, "Paiement", c["nom"], f"Abonnement {db.fmt_euro(c['abonnement_mensuel'])}"))
            n += 1
    for champ, typ in (("date_renouvellement_domaine", "Domaine"),
                       ("date_renouvellement_hebergement", "Hébergement")):
        d = c[champ]
        if d and today <= d <= fin:
            events.append((d, typ, c["nom"], f"Renouvellement {typ.lower()}"
                                              + (f" ({c['domaine']})" if typ == "Domaine" and c["domaine"] else "")))
for t in db.taches():
    d = t["date_limite"]
    if t["statut"] != "valide" and t["client_id"] in clients and d and today <= d <= fin:
        events.append((d, "Tâche", clients[t["client_id"]]["nom"], t["titre"]))

if not events:
    st.info("Aucune échéance dans les 90 prochains jours.")
    st.stop()

df = pd.DataFrame(events, columns=["Date", "Type", "Client", "Libellé"]).sort_values(["Date", "Type"])
df["Semaine"] = df["Date"].map(lambda x: x - timedelta(days=x.weekday()))  # lundi de la semaine

# --- Carte à barres : total par type ------------------------------------------
comptes = df["Type"].value_counts()
g, d = st.columns([1, 2])
with g:
    ui.carte_barres("Échéances sur 90 jours",
                    [(t, int(comptes.get(t, 0)), coul) for t, coul in COULEURS.items()])

# --- Graphique : nombre d'échéances par semaine et par type -------------------
par_semaine = df.groupby(["Semaine", "Type"]).size().reset_index(name="Échéances")
par_semaine["Semaine"] = pd.to_datetime(par_semaine["Semaine"])
fig = px.bar(par_semaine, x="Semaine", y="Échéances", color="Type",
             color_discrete_map=COULEURS, category_orders={"Type": list(COULEURS)})
fig.update_layout(
    template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
    font=dict(family="Inter, sans-serif", color=ui.TEXTE), height=300,
    margin=dict(l=4, r=4, t=4, b=4), legend=dict(orientation="h", y=-0.25, title=None),
    bargap=0.25, xaxis_title=None, yaxis_title=None,
)
fig.update_xaxes(tickformat="%d/%m", gridcolor="rgba(0,0,0,0)")
fig.update_yaxes(dtick=1, gridcolor="#edf1f7")
with d, st.container(border=True, key="carte_graph"):
    st.markdown("**Échéances par semaine**")
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False})

# --- Tableau groupé par semaine ------------------------------------------------
EMOJI = {"Paiement": "💶", "Domaine": "🌐", "Hébergement": "🖥️", "Tâche": "📌"}
for semaine, groupe in df.groupby("Semaine"):
    titre = "Cette semaine" if semaine <= today else f"Semaine du {semaine:%d/%m}"
    st.markdown(f"#### {titre} · {len(groupe)} échéance(s)")
    vue = groupe.assign(Type=groupe["Type"].map(lambda t: f"{EMOJI[t]} {t}"))[
        ["Date", "Type", "Client", "Libellé"]]
    st.dataframe(vue, hide_index=True, width="stretch",
                 column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY")})

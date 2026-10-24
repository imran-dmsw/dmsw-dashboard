"""✅ Aujourd'hui : tâches en retard, tâches de la semaine, alertes automatiques."""
from datetime import date, timedelta

import streamlit as st

import alerts
import clickup_client as cu
import db
import ui
from ui import esc, fmt_date


today = date.today()
p = db.parametres()
horizon = today + timedelta(days=p["taches_horizon_jours"])
ui.entete("Priorités", "Aujourd'hui",
          f"{today:%d/%m/%Y} · ce qui est en retard, ce qui tombe cette semaine et les alertes à traiter.")

clients = {c["id"]: c for c in db.clients() if c["statut_projet"] != "archive"}
ouvertes = [t for t in db.taches() if t["statut"] != "valide" and t["client_id"] in clients]
PRIO = {"urgente": 0, "haute": 1, "normale": 2, "basse": 3}


def tri(t):
    return (t["date_limite"], PRIO.get(t["priorite"], 2))


en_retard = sorted([t for t in ouvertes if t["date_limite"] and t["date_limite"] < today], key=tri)
semaine = sorted([t for t in ouvertes if t["date_limite"] and today <= t["date_limite"] <= horizon], key=tri)
liste_alertes = alerts.toutes_alertes(list(clients.values()), p, today)


def ligne_tache(t, niveau):
    c = clients[t["client_id"]]
    with st.container(border=True, key=f"carte_today_{t['id']}"):
        a, b, d = st.columns([5, 2, 1.3], vertical_alignment="center")
        a.markdown(f"{ui.EMOJI_VOYANT[niveau]} **{esc(t['titre'])}**  \n"
                   f"<span class='muted'>{esc(c['nom'])} · {db.TACHE_STATUTS[t['statut']]} · "
                   f"priorité {db.PRIORITES[t['priorite']].lower()}</span>", unsafe_allow_html=True)
        jours = (t["date_limite"] - today).days
        rel = "aujourd'hui" if jours == 0 else (f"il y a {-jours} j" if jours < 0 else f"dans {jours} j")
        b.markdown(f"{fmt_date(t['date_limite'])}  \n<span class='muted'>{rel}</span>",
                   unsafe_allow_html=True)
        if d.button("✔ Fait", key=f"done_{t['id']}", width="stretch"):
            db.set_tache_statut(t, "valide", "moi")
            ui.flash(f"« {t['titre']} » validée.")
            st.rerun()


if en_retard:
    ui.bandeau("rouge", f"{len(en_retard)} tâche(s) en retard à rattraper en priorité.")
elif any(a["niveau"] == "rouge" for a in liste_alertes):
    ui.bandeau("rouge", "Aucune tâche en retard, mais des alertes urgentes à traiter.")
elif semaine or liste_alertes:
    ui.bandeau("orange", "Rien en retard : avance sur la semaine et les points à surveiller.")

ui.kpis([
    ("En retard", len(en_retard), "rouge" if en_retard else ""),
    (f"À faire d'ici {p['taches_horizon_jours']} j", len(semaine), "accent"),
    ("Alertes", len(liste_alertes), "rouge" if any(a["niveau"] == "rouge" for a in liste_alertes) else ""),
])

if not (en_retard or semaine or liste_alertes):
    ui.bandeau("ok", "Tout est à jour 🎉 Aucun retard, aucune alerte. Profite pour prospecter ou souffler un peu !")

if en_retard:
    st.markdown("### 1. Tâches en retard")
    for t in en_retard:
        ligne_tache(t, "rouge")

if semaine:
    st.markdown("### 2. Aujourd'hui et cette semaine")
    for t in semaine:
        ligne_tache(t, "orange" if t["date_limite"] == today else "ok")

if liste_alertes:
    st.markdown("### 3. Alertes automatiques")
    for i, a in enumerate(liste_alertes):
        col1, col2 = st.columns([6, 1.3], vertical_alignment="center")
        col1.markdown(ui.alerte_html(a, avec_client=True), unsafe_allow_html=True)
        if col2.button("Fiche", key=f"al_{i}",
                       width="stretch"):
            st.session_state["client_id"] = a["client_id"]
            st.switch_page("views/client.py")


# --- Sprint ClickUp : tâches dues aujourd'hui ou en retard -----------------------
# Les tâches déjà liées au dashboard apparaissent plus haut : on ne les répète pas.
st.markdown("### Sprint ClickUp")
sprint, erreur = ui.taches_sprint()
if sprint is None:
    if erreur:
        st.error(erreur)
    else:
        ui.clickup_non_configure()
else:
    liees = {t["clickup_task_id"] for t in db.taches() if t["clickup_task_id"]}
    jour = cu.aujourd_hui_paris()
    dues = sorted([t for t in sprint if t["id"] not in liees and cu.due_bientot(t, 0, jour)],
                  key=lambda t: t["date_limite"])
    if not dues:
        st.caption("Rien de dû aujourd'hui ni en retard dans le sprint ClickUp 👌")
    for t in dues:
        with st.container(border=True, key=f"carte_sprint_{t['id']}"):
            a, b, d = st.columns([5, 2, 1.3], vertical_alignment="center")
            niveau = "rouge" if cu.en_retard(t, jour) else "orange"
            a.markdown(f"{ui.EMOJI_VOYANT[niveau]} **{esc(t['nom'])}**  \n"
                       f"<span class='muted'>ClickUp · {esc(t['statut'])}</span>", unsafe_allow_html=True)
            b.markdown(fmt_date(t["date_limite"]))
            d.link_button("Ouvrir ↗", t["url"], width="stretch")

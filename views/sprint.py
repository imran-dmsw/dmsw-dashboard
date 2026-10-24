"""🗂️ Sprint ClickUp : tâches de la liste du sprint, filtres, rafraîchissement."""
import pandas as pd
import streamlit as st

import clickup_client as cu
import db
import ui
import sync

ui.entete("ClickUp", "Sprint ClickUp", "Les tâches de ta liste de sprint, lues directement dans ClickUp.")

if not cu.configure():
    ui.clickup_non_configure()
    st.stop()

if st.button("🔄 Rafraîchir"):
    cu.vider_cache()
    ui.flash("Tâches ClickUp rechargées.")
    st.rerun()

try:
    taches = cu.taches_liste(cu.list_id(), True)
except cu.ClickUpError as e:
    st.error(str(e))
    st.stop()

today = cu.aujourd_hui_paris()
retard = [t for t in taches if cu.en_retard(t, today)]
ouvertes = [t for t in taches if t["statut_type"] != "closed"]
ui.kpis([
    ("Tâches ouvertes", len(ouvertes), "accent"),
    ("En retard", len(retard), "rouge" if retard else ""),
    ("Dues aujourd'hui", sum(t["date_limite"] == today for t in ouvertes), ""),
])

# --- Filtres -----------------------------------------------------------------
f1, f2, f3, f4 = st.columns([2, 2, 1.2, 1.2], vertical_alignment="bottom")
statuts = sorted({t["statut"] for t in taches})
choix_statuts = f1.multiselect("Statut", statuts, default=[])
prios = {None: "Aucune", 1: "Urgente", 2: "Haute", 3: "Normale", 4: "Basse"}
choix_prios = f2.multiselect("Priorité", list(prios), format_func=prios.get, default=[])
fermees = f3.toggle("Inclure les fermées")
retard_seul = f4.toggle("En retard uniquement")

liees = {t["clickup_task_id"] for t in db.taches() if t["clickup_task_id"]}
lignes = []
for t in taches:
    if not fermees and t["statut_type"] == "closed":
        continue
    if choix_statuts and t["statut"] not in choix_statuts:
        continue
    if choix_prios and t["priorite"] not in choix_prios:
        continue
    if retard_seul and not cu.en_retard(t, today):
        continue
    lignes.append({
        "": "🔴" if cu.en_retard(t, today) else "",
        "Tâche": t["nom"],
        "Statut": t["statut"],
        "Priorité": prios.get(t["priorite"], "—"),
        "Date limite": ui.fmt_date(t["date_limite"]),
        "Dashboard": "🔗 liée" if t["id"] in liees else "",
        "Lien": t["url"],
    })

if not lignes:
    st.info("Aucune tâche ne correspond aux filtres.")
    st.stop()

st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch", column_config={
    "": st.column_config.TextColumn(width="small"),
    "Lien": st.column_config.LinkColumn("Lien", display_text="Ouvrir ↗"),
})
st.caption(f"{len(lignes)} tâche(s) · les lectures sont gardées en cache 5 minutes.")
if not sync.reglages()["mapping"]:
    st.caption("Astuce : configure la correspondance des statuts dans ⚙️ Paramètres pour activer la synchro.")

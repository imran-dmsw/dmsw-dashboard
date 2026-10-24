"""🔗 Synchronisation ClickUp : état, journal, points à vérifier, liaison manuelle."""
import pandas as pd
import streamlit as st

import clickup_client as cu
import db
import sync
import ui

ui.entete("ClickUp", "Synchronisation",
          "Les tâches liées se mettent à jour dans les deux sens : la modification la plus récente gagne.")

if not cu.configure():
    ui.clickup_non_configure()
    st.stop()

regl = sync.reglages()
taches = db.taches()
taches_par_id = {t["id"]: t for t in taches}
clients = {c["id"]: c for c in db.clients()}
logs = db.sync_log()

# --- État --------------------------------------------------------------------------
if regl["simulation"]:
    ui.bandeau("orange", "Mode simulation actif : la synchro montre ce qu'elle ferait, sans rien écrire.")
elif not regl["mapping"]:
    ui.bandeau("orange", "Correspondance des statuts non configurée (⚙️ Paramètres) : "
                         "les statuts ne sont pas synchronisés, les autres champs oui.")
else:
    ui.bandeau("ok", "Synchronisation active. Automatique au chargement toutes les 5 minutes.")

derniere = sync.derniere_synchro()
ok = [l for l in logs if l["resultat"] in ("ok", "envoyé", "importé")]
ui.kpis([
    ("Dernière synchro", derniere.strftime("%d/%m %H:%M") if derniere else "jamais", "accent"),
    ("Tâches liées", sum(bool(t["clickup_task_id"]) for t in taches), ""),
    ("Changements → ClickUp", sum(l["direction"] == "vers_clickup" for l in ok), ""),
    ("Changements ← ClickUp", sum(l["direction"] == "depuis_clickup" for l in ok), ""),
    ("Conflits ouverts", sum(l["resultat"] == "conflit" for l in logs), ""),
    ("Erreurs", sum((l["resultat"] or "").startswith("erreur") for l in logs[:50]), ""),
])

# --- Synchroniser ------------------------------------------------------------------
a, b = st.columns(2)
if a.button("🔄 Synchroniser maintenant", type="primary", width="stretch"):
    try:
        st.session_state["_resultat_sync"] = sync.synchroniser()
    except cu.ClickUpError as e:
        st.error(str(e))
if regl["simulation"]:
    if b.button("Passer en mode réel", width="stretch"):
        db.set_reglages({sync.R_SIMULATION: "0"})
        ui.flash("Mode réel activé : la prochaine synchro écrira vraiment.")
        st.rerun()

res = st.session_state.pop("_resultat_sync", None)
if res:
    par_id = {t["id"]: t for t in res["taches"]}
    phrases = [sync.resume_action(x, par_id) for x in res["plan"]]
    if res["simulation"]:
        st.markdown("#### Aperçu (simulation, rien n'a été écrit)")
        if phrases:
            st.markdown("\n".join(f"- {p}" for p in phrases))
        else:
            st.success("Rien à faire : tout est déjà synchronisé.")
    else:
        s = res["stats"]
        st.success(f"Synchro terminée : {s['vers_clickup']} changement(s) vers ClickUp, "
                   f"{s['depuis_clickup']} depuis ClickUp, {s['conflits']} conflit(s), {s['erreurs']} erreur(s).")

# --- À vérifier ----------------------------------------------------------------------
st.markdown("### À vérifier")
deliees = [t for t in taches if t["clickup_delie"]]
conflits = [l for l in logs if l["resultat"] == "conflit"]
erreurs = [l for l in logs[:50] if (l["resultat"] or "").startswith("erreur")]
if not (deliees or conflits or erreurs):
    st.caption("Rien à vérifier 👌")
for t in deliees:
    nom = clients.get(t["client_id"], {}).get("nom", "?")
    st.markdown(f'<div class="alerte" style="border-left-color:{ui.ORANGE}">🟠 <b>{ui.esc(nom)}</b> — '
                f'« {ui.esc(t["titre"])} » est déliée : introuvable dans la liste ClickUp. '
                f'Rien n\'a été supprimé.</div>', unsafe_allow_html=True)
for l in conflits:
    t = taches_par_id.get(l["tache_id"])
    titre = t["titre"] if t else "tâche supprimée"
    with st.container(border=True, key=f"carte_conflit_{l['id']}"):
        st.markdown(f"⚖️ **{ui.esc(titre)}** — {sync.LIBELLES_CHAMPS.get(l['champ'], l['champ'])} "
                    f"modifié des deux côtés à moins de 2 minutes d'écart.  \n"
                    f"Dashboard : **{ui.esc(l['ancienne_valeur'])}** · ClickUp : **{ui.esc(l['nouvelle_valeur'])}**",
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        for col, garder, label in ((c1, "local", "Garder la version du dashboard"),
                                   (c2, "clickup", "Garder la version ClickUp")):
            if col.button(label, key=f"cf_{garder}_{l['id']}", width="stretch"):
                try:
                    sync.resoudre_conflit(l, garder, regl)
                    ui.flash("Conflit résolu.")
                    st.rerun()
                except cu.ClickUpError as e:
                    st.error(str(e))
for l in erreurs[:10]:
    st.markdown(f'<div class="alerte" style="border-left-color:{ui.ROUGE}">🔴 '
                f'{l["date"]:%d/%m %H:%M} — {ui.esc(l["resultat"])}</div>', unsafe_allow_html=True)

# --- Lier une tâche existante ----------------------------------------------------------
with st.expander("🔗 Lier une tâche existante"):
    try:
        distantes = cu.taches_liste(cu.list_id(), True)
    except cu.ClickUpError as e:
        st.error(str(e))
        distantes = []
    liees = {t["clickup_task_id"] for t in taches if t["clickup_task_id"]}
    libres_loc = [t for t in taches if not t["clickup_task_id"]]
    libres_dist = [r for r in distantes if r["id"] not in liees]
    if not libres_loc or not libres_dist:
        st.caption("Aucune paire à lier : toutes les tâches sont déjà liées d'un côté ou de l'autre.")
    else:
        with st.form("lier"):
            loc = st.selectbox("Tâche du dashboard", libres_loc, format_func=lambda t: (
                f"{clients.get(t['client_id'], {}).get('nom', '?')} — {t['titre']}"))
            dist = st.selectbox("Tâche ClickUp", libres_dist, format_func=lambda r: f"{r['nom']} ({r['statut']})")
            if st.form_submit_button("Lier", type="primary"):
                sync.lier(loc, dist)
                ui.flash("Tâches liées. Elles seront comparées à la prochaine synchro.")
                st.rerun()

# --- Journal ----------------------------------------------------------------------------
st.markdown("### Journal (50 derniers événements)")
if not logs:
    st.caption("Aucun événement pour l'instant.")
else:
    st.dataframe(pd.DataFrame([{
        "Date": l["date"].strftime("%d/%m %H:%M") if l["date"] else "",
        "Sens": "→ ClickUp" if l["direction"] == "vers_clickup" else "← ClickUp",
        "Tâche": taches_par_id.get(l["tache_id"], {}).get("titre", "—"),
        "Champ": sync.LIBELLES_CHAMPS.get(l["champ"], l["champ"]),
        "Avant": l["ancienne_valeur"], "Après": l["nouvelle_valeur"], "Résultat": l["resultat"],
    } for l in logs[:50]]), hide_index=True, width="stretch")

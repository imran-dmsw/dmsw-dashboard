"""⚙️ Paramètres : seuils d'alertes, export / import CSV, données de démo."""
import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

import clickup_client as cu
import db
import demo
import import_csv
import sync
import ui

ui.entete("Réglages", "Paramètres",
          "Seuils des alertes, sauvegarde et import CSV, données de démonstration, ClickUp.")

# --- Seuils d'alertes ----------------------------------------------------------
st.markdown("### Seuils des alertes")
p = db.parametres()
LIBELLES = {
    "solde_jours_apres_livraison": "Solde impayé : alerte rouge X jours après la livraison",
    "renouvellement_orange_jours": "Renouvellement domaine / hébergement : orange sous X jours",
    "renouvellement_rouge_jours": "Renouvellement domaine / hébergement : rouge sous X jours",
    "audit_seo_jours": "Audit SEO trop ancien après X jours",
    "taches_horizon_jours": "Page Aujourd'hui : tâches à venir sur X jours",
    "tarif_horaire": "Tarif horaire des corrections hors forfait (€/h)",
}
with st.form("seuils"):
    cols = st.columns(2)
    valeurs = {}
    for i, (cle, lbl) in enumerate(LIBELLES.items()):
        valeurs[cle] = cols[i % 2].number_input(lbl, min_value=0, max_value=3650, step=1, value=int(p[cle]))
    a, b = st.columns(2)
    if a.form_submit_button("Enregistrer les seuils", type="primary", width="stretch"):
        if valeurs["renouvellement_rouge_jours"] > valeurs["renouvellement_orange_jours"]:
            st.error("Le seuil rouge doit être inférieur ou égal au seuil orange.")
        else:
            db.set_parametres(valeurs)
            ui.flash("Seuils enregistrés.")
            st.rerun()
    if b.form_submit_button("Revenir aux valeurs par défaut", width="stretch"):
        db.set_parametres(db.DEFAULT_PARAMETRES)
        ui.flash("Seuils remis par défaut.")
        st.rerun()

# --- Export ----------------------------------------------------------------------
st.markdown("### Sauvegarde (export CSV)")
tables = ["clients", "taches", "historique", "sync_log"]
frames = {t: pd.DataFrame(db.raw_rows(t), columns=["id", *db.TABLES[t]]) for t in tables}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for t, df in frames.items():
        z.writestr(f"{t}.csv", df.to_csv(index=False))
st.download_button(f"⬇️ Tout exporter (zip, {sum(len(f) for f in frames.values())} lignes)",
                   buf.getvalue(), file_name=f"dmsw-sauvegarde-{date.today():%Y-%m-%d}.zip",
                   mime="application/zip", type="primary")
cols = st.columns(len(frames))
for col, (t, df) in zip(cols, frames.items()):
    col.download_button(f"{t}.csv ({len(df)})", df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{t}.csv", mime="text/csv", width="stretch")

# --- Import ----------------------------------------------------------------------
st.markdown("### Import (CSV ou zip)")
st.caption("Dépose clients.csv, taches.csv et historique.csv, ou un .zip qui les contient. "
           "Les tâches et l'historique sont rattachés au client par la colonne client_nom. "
           "Dates acceptées : 2026-10-24 ou 24/10/2026. Relancer l'import ne crée aucun doublon : "
           "un client, une tâche ou une ligne d'historique déjà présents sont ignorés.")
modele = pd.DataFrame(columns=list(import_csv.CHAMPS_CLIENT))
st.download_button("Télécharger un modèle clients.csv vide", modele.to_csv(index=False).encode("utf-8-sig"),
                   file_name="clients.csv", mime="text/csv")
deposes = st.file_uploader("Fichiers", type=["csv", "zip"], accept_multiple_files=True)


def afficher_rapport(r: dict, simulation: bool):
    c = r["crees"]
    verbe = "seront créés" if simulation else "créés"
    st.markdown(f"**{c['clients']} client(s), {c['taches']} tâche(s), {c['historique']} ligne(s) "
                f"d'historique {verbe}.** {len(r['ignores'])} déjà présent(s), ignoré(s).")
    for e in r["erreurs"]:
        st.error(e)
    if r["ignores"]:
        with st.expander(f"Éléments ignorés ({len(r['ignores'])})"):
            st.write("\n".join(f"- {x}" for x in r["ignores"]))


if deposes:
    try:
        tables = import_csv.lire_fichiers([(f.name, f.getvalue()) for f in deposes])
    except Exception as e:
        tables = {}
        st.error(f"Impossible de lire les fichiers : {e}")
    if tables:
        st.caption("Fichiers reconnus : " + ", ".join(f"{k}.csv ({len(v)} lignes)" for k, v in tables.items()))
        apercu = import_csv.importer(tables, simulation=True)
        afficher_rapport(apercu, simulation=True)
        if sum(apercu["crees"].values()) and st.button("Importer", type="primary"):
            r = import_csv.importer(tables)
            ui.flash(f"Import terminé : {r['crees']['clients']} client(s), {r['crees']['taches']} tâche(s), "
                     f"{r['crees']['historique']} ligne(s) d'historique.")
            st.rerun()
    elif deposes:
        st.warning("Aucun fichier reconnu (clients.csv, taches.csv ou historique.csv).")

# --- Démo ------------------------------------------------------------------------
st.markdown("### Données de démonstration")
st.caption("Ajoute 4 faux clients préfixés « [Démo] » (restaurant, avocat, boutique Shopify, "
           "client en maintenance). N'écrase et ne modifie jamais tes vraies données.")
a, b = st.columns(2)
if a.button("Charger des données de démo", type="primary", width="stretch"):
    n = demo.charger()
    if n:
        ui.flash(f"{n} clients de démo ajoutés.")
        st.rerun()
    st.info("Les données de démo sont déjà chargées.")
with b.popover("Supprimer les données de démo", width="stretch"):
    st.write("Supprime uniquement les clients « [Démo] » et leurs tâches / historique.")
    if st.button("Oui, supprimer la démo", type="primary"):
        ui.flash(f"{demo.supprimer()} client(s) de démo supprimé(s).", "🗑")
        st.rerun()

# --- ClickUp ---------------------------------------------------------------------
st.markdown("### ClickUp")
if not cu.configure():
    ui.clickup_non_configure()
else:
    regl = sync.reglages()
    st.caption(f"Liste du sprint : {cu.list_id()} · token configuré (jamais affiché).")
    with st.form("clickup_options"):
        simulation = st.toggle("Mode simulation (la synchro montre ce qu'elle ferait, sans rien écrire)",
                               value=regl["simulation"])
        auto = st.toggle("Envoyer automatiquement les tâches urgentes et à échéance dans la semaine vers ClickUp",
                         value=regl["auto_envoi"])
        imp = st.toggle("Importer les tâches nées dans ClickUp (rattachées au client [Nom] ou à « DMSW (interne) »)",
                        value=regl["import"])
        if st.form_submit_button("Enregistrer les options ClickUp", type="primary"):
            db.set_reglages({sync.R_SIMULATION: "1" if simulation else "0",
                             sync.R_AUTO_ENVOI: "1" if auto else "0", sync.R_IMPORT: "1" if imp else "0"})
            ui.flash("Options ClickUp enregistrées.")
            st.rerun()

    st.markdown("#### Correspondance des statuts")
    try:
        statuts = [s["nom"] for s in cu.statuts_liste(cu.list_id())]
    except cu.ClickUpError as e:
        statuts = []
        st.error(str(e))
    if statuts:
        if not regl["mapping"]:
            st.warning("Tant que la correspondance n'est pas enregistrée, la synchro des statuts est désactivée.")
        actuel = {k: db.reglage(cle) for k, cle in sync.R_MAP.items()}
        with st.form("clickup_mapping"):
            cols = st.columns(3)
            choix = {}
            for col, (local, libelle) in zip(cols, db.TACHE_STATUTS.items()):
                options = [""] + statuts
                choix[local] = col.selectbox(f"« {libelle} » dans ClickUp", options,
                                             index=options.index(actuel[local]) if actuel[local] in options else 0,
                                             format_func=lambda s: s or "— choisir —")
            if st.form_submit_button("Enregistrer la correspondance", type="primary"):
                if not all(choix.values()):
                    st.error("Choisis un statut ClickUp pour chacun des trois statuts.")
                else:
                    db.set_reglages({sync.R_MAP[k]: v for k, v in choix.items()})
                    ui.flash("Correspondance des statuts enregistrée.")
                    st.rerun()

"""⚙️ Paramètres : seuils d'alertes, export / import CSV, données de démo."""
import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

import db
import demo
import ui

ui.entete("Réglages", "Paramètres",
          "Seuils des alertes, sauvegarde et import CSV, données de démonstration.")

# --- Seuils d'alertes ----------------------------------------------------------
st.markdown("### Seuils des alertes")
p = db.parametres()
LIBELLES = {
    "solde_jours_apres_livraison": "Solde impayé : alerte rouge X jours après la livraison",
    "renouvellement_orange_jours": "Renouvellement domaine / hébergement : orange sous X jours",
    "renouvellement_rouge_jours": "Renouvellement domaine / hébergement : rouge sous X jours",
    "audit_seo_jours": "Audit SEO trop ancien après X jours",
    "sauvegarde_jours": "Sauvegarde / mise à jour trop ancienne après X jours (maintenance)",
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
tables = ["clients", "taches", "historique"]
frames = {t: pd.DataFrame(db.raw_rows(t), columns=["id", *db.TABLES[t]]) for t in tables}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for t, df in frames.items():
        z.writestr(f"{t}.csv", df.to_csv(index=False))
st.download_button(f"⬇️ Tout exporter (zip, {sum(len(f) for f in frames.values())} lignes)",
                   buf.getvalue(), file_name=f"dmsw-sauvegarde-{date.today():%Y-%m-%d}.zip",
                   mime="application/zip", type="primary")
cols = st.columns(3)
for col, (t, df) in zip(cols, frames.items()):
    col.download_button(f"{t}.csv ({len(df)})", df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{t}.csv", mime="text/csv", width="stretch")

# --- Import ----------------------------------------------------------------------
st.markdown("### Import de clients (CSV)")
st.caption("Colonnes reconnues : celles du modèle (nom, activite, site_url, prix_site, "
           "date_livraison…). La colonne « nom » est obligatoire. Les autres colonnes sont ignorées. "
           "Dates acceptées : 2026-10-24 ou 24/10/2026. Chaque ligne crée un nouveau client.")
modele = pd.DataFrame(columns=[c for c in db.CLIENT_FIELDS if c != "created_at"])
st.download_button("Télécharger un modèle CSV vide", modele.to_csv(index=False).encode("utf-8-sig"),
                   file_name="modele-clients.csv", mime="text/csv")
fichier = st.file_uploader("Fichier CSV", type="csv")
def importer(fichier):
    """Lit, valide et importe le CSV (return = on s'arrête là)."""
    try:
        df = pd.read_csv(fichier, sep=None, engine="python", dtype=str, encoding="utf-8-sig").fillna("")
    except Exception as e:
        st.error(f"Impossible de lire le fichier : {e}")
        return
    df.columns = [c.strip() for c in df.columns]
    connues = [c for c in df.columns if c in db.CLIENT_FIELDS and c != "created_at"]
    if "nom" not in connues:
        st.error("La colonne « nom » est obligatoire.")
        return
    ignorees = [c for c in df.columns if c not in connues]
    if ignorees:
        st.warning("Colonnes ignorées : " + ", ".join(ignorees))

    lignes, erreurs = [], []
    for i, row in df[connues].iterrows():
        data, probleme = {}, None
        for col in connues:
            v = row[col].strip()
            typ = db.CLIENT_FIELDS[col]
            if v == "":
                continue
            if typ == "date":
                d = db.to_date(v)
                if d is None:
                    probleme = f"date invalide en « {col} » ({v})"
                data[col] = d
            elif typ == "float":
                try:
                    data[col] = float(v.replace(" ", "").replace(",", ".").replace("€", ""))
                except ValueError:
                    probleme = f"nombre invalide en « {col} » ({v})"
            elif typ == "int":
                try:
                    data[col] = int(float(v.replace(",", ".")))
                except ValueError:
                    probleme = f"entier invalide en « {col} » ({v})"
            elif typ == "bool":
                data[col] = db.to_bool(v)
            else:
                data[col] = v
        if not data.get("nom"):
            probleme = "nom manquant"
        for champ, choix in (("statut_projet", db.STATUTS_PROJET), ("seo_statut", db.SEO_STATUTS),
                             ("fiche_google_statut", db.FICHE_GOOGLE_STATUTS)):
            if champ in data and data[champ] not in choix:
                probleme = f"valeur inconnue en « {champ} » ({data[champ]})"
        if probleme:
            erreurs.append(f"Ligne {i + 2} : {probleme}")
        else:
            lignes.append(data)

    st.dataframe(df[connues].head(20), hide_index=True, width="stretch")
    for e in erreurs:
        st.error(e)
    if lignes and st.button(f"Importer {len(lignes)} client(s)", type="primary"):
        for data in lignes:
            if "solde_restant" not in data and "prix_site" in data:
                data["solde_restant"] = max(data["prix_site"] - data.get("acompte_recu", 0), 0)
            db.create_client(data)
        ui.flash(f"{len(lignes)} client(s) importé(s).")
        st.rerun()


if fichier is not None:
    importer(fichier)

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

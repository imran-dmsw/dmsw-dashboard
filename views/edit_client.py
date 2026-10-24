"""➕ Nouveau client / Modifier : formulaire complet en sections repliables."""
from datetime import date, timedelta

import streamlit as st

import db
import ui

# Checklist de démarrage proposée à la création (titre, délai en jours)
CHECKLIST = [
    ("Devis signé et acompte reçu", 0),
    ("Brief et contenus récupérés", 7),
    ("Maquette ou site démo validé", 14),
    ("Mentions légales et RGPD", 21),
    ("Fiche Google Business", 21),
    ("Formulaire de contact testé", 25),
    ("Mise en ligne et HTTPS", 28),
    ("Proposer la maintenance à 29,99 €/mois", 30),
]

ui.entete("Clients", "Nouveau client / Modifier",
          "Crée une fiche complète ou mets à jour un client existant. Seul le nom est obligatoire.")

# --- Choix : nouveau client ou client existant -------------------------------
clients = db.clients()
options = [None] + [c["id"] for c in clients]
noms = {c["id"]: c["nom"] for c in clients}
if st.session_state.pop("edit_mode", None) == "nouveau":
    defaut = None
else:
    defaut = st.session_state.get("edit_client_id")
choix = st.selectbox(
    "Fiche à remplir", options, index=options.index(defaut) if defaut in options else 0,
    format_func=lambda i: "➕ Nouveau client" if i is None else f"✏️ {noms[i]}",
)
st.session_state["edit_client_id"] = choix
c = db.client(choix) if choix else {**db.CLIENT_DEFAULTS}
nouveau = choix is None


def sel(label, choices: dict, valeur, key):
    keys = list(choices)
    return st.selectbox(label, keys, index=keys.index(valeur) if valeur in keys else 0,
                        format_func=choices.get, key=key)


with st.form(f"form_client_{choix}"):
    with st.expander("🪪 Identité", expanded=True):
        a, b = st.columns(2)
        nom = a.text_input("Nom du client *", c.get("nom") or "")
        activite = b.text_input("Activité", c.get("activite") or "", placeholder="Restaurant, avocat…")
        site_url = a.text_input("Adresse du site", c.get("site_url") or "", placeholder="https://…")
        domaine = b.text_input("Nom de domaine", c.get("domaine") or "")
        contact_nom = a.text_input("Contact", c.get("contact_nom") or "")
        contact_tel = b.text_input("Téléphone", c.get("contact_tel") or "")
        contact_email = a.text_input("Email", c.get("contact_email") or "")
        statut_projet = b.selectbox(
            "Statut du projet", list(db.STATUTS_PROJET), format_func=db.STATUTS_PROJET.get,
            index=list(db.STATUTS_PROJET).index(c.get("statut_projet") or "prospect"))
        date_livraison = a.date_input("Date de livraison", c.get("date_livraison"), format="DD/MM/YYYY")
        notes = st.text_area("Notes", c.get("notes") or "")

    with st.expander("💶 Argent"):
        a, b = st.columns(2)
        prix_site = a.number_input("Prix du site (€)", 0.0, step=50.0, value=float(c.get("prix_site") or 0))
        acompte = b.number_input("Acompte reçu (€)", 0.0, step=50.0, value=float(c.get("acompte_recu") or 0))
        solde_auto = st.checkbox("Calculer le solde automatiquement (prix − acompte)", value=True)
        solde_manuel = a.number_input("Solde restant (€), si non calculé", 0.0, step=50.0,
                                      value=float(c.get("solde_restant") or 0))
        abonnement = b.number_input("Abonnement mensuel (€, 0 si aucun)", 0.0, step=1.0,
                                    value=float(c.get("abonnement_mensuel") or 0))
        date_prochain_paiement = a.date_input("Prochain paiement", c.get("date_prochain_paiement"),
                                              format="DD/MM/YYYY")
        paiement_a_jour = b.checkbox("Paiement à jour", value=bool(c.get("paiement_a_jour", True)))

    with st.expander("🛠️ Technique"):
        a, b = st.columns(2)
        hebergeur = a.text_input("Hébergeur", c.get("hebergeur") or "")
        stack = b.text_input("Stack", c.get("stack") or "", placeholder="Lovable, Shopify, WordPress…")
        d_dom = a.date_input("Renouvellement domaine", c.get("date_renouvellement_domaine"), format="DD/MM/YYYY")
        d_heb = b.date_input("Renouvellement hébergement", c.get("date_renouvellement_hebergement"),
                             format="DD/MM/YYYY")
        emplacement_acces = st.text_input(
            "Où sont rangés les accès", c.get("emplacement_acces") or "",
            placeholder="Gestionnaire de mots de passe, dossier X — jamais le mot de passe lui-même")

    with st.expander("🔎 SEO"):
        seo_statut = sel("Statut SEO", db.SEO_STATUTS, c.get("seo_statut"), "f_seo")
        fiche_google = sel("Fiche Google", db.FICHE_GOOGLE_STATUTS, c.get("fiche_google_statut"), "f_fg")
        search_console = st.checkbox("Search Console branchée", value=bool(c.get("search_console")))
        audit = st.date_input("Dernier audit SEO", c.get("date_dernier_audit_seo"), format="DD/MM/YYYY")
        seo_notes = st.text_area("Notes SEO", c.get("seo_notes") or "")

    with st.expander("🔐 Sécurité"):
        a, b = st.columns(2)
        https_actif = a.checkbox("HTTPS actif", value=bool(c.get("https_actif")))
        double_auth = b.checkbox("Double authentification", value=bool(c.get("double_auth")))
        sauvegarde = a.date_input("Dernière sauvegarde", c.get("date_derniere_sauvegarde"), format="DD/MM/YYYY")
        maj = b.date_input("Dernière mise à jour", c.get("date_derniere_mise_a_jour"), format="DD/MM/YYYY")
        securite_notes = st.text_area("Notes sécurité", c.get("securite_notes") or "")

    with st.expander("📋 Suivi"):
        a, b = st.columns(2)
        corr_incl = a.number_input("Corrections incluses", 0, step=1, value=int(c.get("corrections_incluses") or 0))
        corr_util = b.number_input("Corrections utilisées", 0, step=1, value=int(c.get("corrections_utilisees") or 0))

    coches = []
    if nouveau:
        with st.expander("🚀 Checklist de démarrage (tâches créées)", expanded=True):
            st.caption("Coche les étapes à ajouter comme tâches. Dates limites indicatives à partir d'aujourd'hui.")
            for titre, delai in CHECKLIST:
                if st.checkbox(f"{titre}  ·  J+{delai}", value=True, key=f"chk_{titre}"):
                    coches.append((titre, delai))

    envoyer = st.form_submit_button("Créer le client" if nouveau else "Enregistrer",
                                    type="primary", width="stretch")

if envoyer:
    erreurs = []
    if not nom.strip():
        erreurs.append("Le nom du client est obligatoire.")
    if acompte > prix_site and prix_site > 0:
        erreurs.append("L'acompte dépasse le prix du site.")
    if corr_util < 0 or corr_incl < 0:
        erreurs.append("Les corrections ne peuvent pas être négatives.")
    if date_livraison and date_livraison > date.today() + timedelta(days=3650):
        erreurs.append("Date de livraison invalide.")
    for e in erreurs:
        st.error(e)

    if not erreurs:
        data = {
            "nom": nom.strip(), "activite": activite, "site_url": site_url, "domaine": domaine,
            "contact_nom": contact_nom, "contact_tel": contact_tel, "contact_email": contact_email,
            "date_livraison": date_livraison, "statut_projet": statut_projet, "notes": notes,
            "prix_site": prix_site, "acompte_recu": acompte,
            "solde_restant": max(prix_site - acompte, 0.0) if solde_auto else solde_manuel,
            "abonnement_mensuel": abonnement, "date_prochain_paiement": date_prochain_paiement,
            "paiement_a_jour": paiement_a_jour, "hebergeur": hebergeur, "stack": stack,
            "date_renouvellement_domaine": d_dom, "date_renouvellement_hebergement": d_heb,
            "emplacement_acces": emplacement_acces, "seo_statut": seo_statut,
            "fiche_google_statut": fiche_google, "search_console": search_console,
            "date_dernier_audit_seo": audit, "seo_notes": seo_notes, "https_actif": https_actif,
            "double_auth": double_auth, "date_derniere_sauvegarde": sauvegarde,
            "date_derniere_mise_a_jour": maj, "securite_notes": securite_notes,
            "corrections_incluses": corr_incl, "corrections_utilisees": corr_util,
        }
        if nouveau:
            cid = db.create_client(data)
            for titre, delai in coches:
                db.create_tache({"client_id": cid, "titre": titre,
                                 "date_limite": date.today() + timedelta(days=delai)})
            ui.flash(f"Client « {data['nom']} » créé avec {len(coches)} tâche(s).")
        else:
            cid = choix
            if c.get("statut_projet") != statut_projet:
                db.add_historique(cid, "note", f"Statut projet : {db.STATUTS_PROJET[c['statut_projet']]} "
                                               f"→ {db.STATUTS_PROJET[statut_projet]}.")
            db.update_client(cid, data)
            ui.flash("Fiche enregistrée.")
        st.session_state["client_id"] = cid
        st.switch_page("views/client.py")

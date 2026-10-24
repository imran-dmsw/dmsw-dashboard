"""👤 Fiche client : en-tête + onglets Résumé, Tâches, Argent, SEO, Technique, Historique."""
from datetime import date

import streamlit as st

import alerts
import clickup_client as cu
import db
import sync
import ui
from ui import esc, fmt_date

today = date.today()
p = db.parametres()

c = ui.client_selector("Client", key="fiche_client")
if not c:
    st.info("Aucun client. Crée-en un depuis « Nouveau / Modifier ».")
    st.stop()
cid = c["id"]
al = alerts.alertes_client(c, p, today)

# --- En-tête -----------------------------------------------------------------
lien = ""
if c["site_url"]:
    url = c["site_url"] if c["site_url"].startswith(("http://", "https://")) else f"https://{c['site_url']}"
    lien = f' · <a href="{esc(url)}" target="_blank">{esc(c["site_url"])} ↗</a>'
ui.entete("Fiche client", c["nom"],
          f'<span class="badge">{esc(db.STATUTS_PROJET.get(c["statut_projet"]))}</span> '
          f'{esc(c["activite"] or "")}{lien}', phrase_html=True)

# Bandeau d'état : la pire alerte du client
pire = alerts.voyant(al)
if pire == "ok":
    ui.bandeau("ok", "Rien à signaler sur ce client.")
else:
    nb = sum(a["niveau"] == pire for a in al)
    ui.bandeau(pire, f"{nb} alerte(s) {'urgente(s)' if pire == 'rouge' else 'à surveiller'} — "
                     f"{next(a['message'] for a in al if a['niveau'] == pire)}")
st.markdown(" ".join(ui.voyant_html(alerts.voyant(al, cat), lbl)
                     for cat, lbl in alerts.CATEGORIES.items() if cat != "suivi"),
            unsafe_allow_html=True)
b_modif, b_suppr, _ = st.columns([1.7, 1.5, 1.6])
if b_modif.button("✏️ Modifier la fiche complète", width="stretch"):
    st.session_state["edit_client_id"] = cid
    st.switch_page("views/edit_client.py")
with b_suppr.popover("🗑 Supprimer ce client", width="stretch"):
    nb_t = len(db.taches(cid))
    st.markdown(f"**Suppression définitive** de « {esc(c['nom'])} », de ses {nb_t} tâche(s) et de "
                f"son historique. Les tâches ClickUp liées ne sont pas supprimées.  \n"
                f"Pour garder une trace sans l'afficher, préfère le statut « Archivé ».",
                unsafe_allow_html=True)
    confirmation = st.text_input("Tape le nom du client pour confirmer", key=f"suppr_{cid}")
    if st.button("Supprimer définitivement", type="primary", key=f"suppr_ok_{cid}",
                 disabled=confirmation.strip() != c["nom"].strip()):
        db.delete_client(cid)
        st.session_state.pop("client_id", None)
        ui.flash(f"Client « {c['nom']} » supprimé.", "🗑")
        st.switch_page("views/overview.py")

t_resume, t_taches, t_argent, t_seo, t_tech, t_histo = st.tabs(
    ["Résumé", "Tâches", "Argent", "SEO", "Technique", "Historique"])

# --- Résumé ------------------------------------------------------------------
with t_resume:
    taches = db.taches(cid)
    action = ui.prochaine_action(taches)
    ui.kpis([
        ("Prochaine action", action["titre"] if action else "—", "accent"),
        ("Date limite", fmt_date(action["date_limite"]) if action else "—", ""),
        ("Tâches ouvertes", sum(t["statut"] != "valide" for t in taches), ""),
    ])
    nb_val = sum(t["statut"] == "valide" for t in taches)
    incl = max(c["corrections_incluses"], c["corrections_utilisees"], 1)
    ui.carte_barres("Avancement", [
        (f"Tâches validées ({nb_val}/{len(taches)})", nb_val, ui.BLEU),
        (f"Corrections utilisées ({c['corrections_utilisees']}/{c['corrections_incluses']})",
         c["corrections_utilisees"],
         ui.ORANGE if c["corrections_utilisees"] >= c["corrections_incluses"] > 0 else ui.BLEU),
    ], maximum=max(len(taches), incl))
    a, b = st.columns(2)
    with a:
        st.markdown("#### Contact")
        st.markdown(f"**{esc(c['contact_nom'] or '—')}**  \n"
                    f"📞 {esc(c['contact_tel'] or '—')}  \n✉️ {esc(c['contact_email'] or '—')}")
        st.markdown(f"Livraison : **{fmt_date(c['date_livraison'])}**  \n"
                    f"Domaine : {esc(c['domaine'] or '—')}  \nStack : {esc(c['stack'] or '—')}")
        if c["notes"]:
            st.markdown("#### Notes")
            st.write(c["notes"])
    with b:
        st.markdown("#### Alertes")
        if al:
            st.markdown("".join(ui.alerte_html(x) for x in al), unsafe_allow_html=True)
        else:
            st.success("Rien à signaler sur ce client 👌")

# --- Tâches (kanban) ---------------------------------------------------------
ORDRE = ["a_faire", "en_cours", "valide"]
PRIO_EMOJI = {"basse": "⚪", "normale": "🔵", "haute": "🟠", "urgente": "🔴"}

with t_taches:
    with st.expander("➕ Nouvelle tâche"):
        with st.form(f"new_task_{cid}", clear_on_submit=True):
            titre = st.text_input("Titre *")
            desc = st.text_area("Description", height=80)
            a, b = st.columns(2)
            prio = a.selectbox("Priorité", list(db.PRIORITES), index=1, format_func=db.PRIORITES.get)
            limite = b.date_input("Date limite", None, format="DD/MM/YYYY")
            if st.form_submit_button("Ajouter", type="primary"):
                if not titre.strip():
                    st.error("Le titre est obligatoire.")
                else:
                    db.create_tache({"client_id": cid, "titre": titre.strip(), "description": desc,
                                     "priorite": prio, "date_limite": limite})
                    db.add_historique(cid, "tache", f"Tâche « {titre.strip()} » créée.")
                    ui.flash("Tâche ajoutée.")
                    st.rerun()

    cols = st.columns(3)
    for col, statut in zip(cols, ORDRE):
        liste = sorted([t for t in db.taches(cid) if t["statut"] == statut],
                       key=lambda t: (t["date_limite"] or date.max, t["id"]))
        with col:
            st.markdown(f"##### {db.TACHE_STATUTS[statut]} ({len(liste)})")
            if not liste:
                st.caption("Aucune tâche.")
            for t in liste:
                tid = t["id"]
                with st.container(border=True, key=f"carte_tache_{tid}"):
                    retard = (t["date_limite"] and t["date_limite"] < today and statut != "valide")
                    date_txt = fmt_date(t["date_limite"]) if t["date_limite"] else "sans date"
                    st.markdown(
                        f"{PRIO_EMOJI.get(t['priorite'], '')} **{esc(t['titre'])}**  \n"
                        f"<span class='muted'>{'🔴 en retard · ' if retard else ''}{date_txt}"
                        f"{' · validé par ' + esc(db.VALIDE_PAR.get(t['valide_par'], '')) if statut == 'valide' and t['valide_par'] else ''}"
                        f"</span>", unsafe_allow_html=True)
                    if t["description"]:
                        st.caption(t["description"])
                    b1, b2, b3, b4 = st.columns(4)
                    i = ORDRE.index(statut)
                    if i > 0 and b1.button("◀", key=f"prev_{tid}", help="Reculer"):
                        db.set_tache_statut(t, ORDRE[i - 1])
                        st.rerun()
                    if i < 2 and b2.button("▶", key=f"next_{tid}", help="Avancer"):
                        db.set_tache_statut(t, ORDRE[i + 1])
                        st.rerun()
                    with b3.popover("✏️", help="Modifier"):
                        with st.form(f"edit_task_{tid}"):
                            n_titre = st.text_input("Titre", t["titre"])
                            n_desc = st.text_area("Description", t["description"] or "")
                            n_prio = st.selectbox("Priorité", list(db.PRIORITES),
                                                  index=list(db.PRIORITES).index(t["priorite"]),
                                                  format_func=db.PRIORITES.get)
                            n_date = st.date_input("Date limite", t["date_limite"], format="DD/MM/YYYY")
                            n_statut = st.selectbox("Statut", ORDRE, index=i, format_func=db.TACHE_STATUTS.get)
                            n_par = st.selectbox("Validé par", list(db.VALIDE_PAR),
                                                 index=list(db.VALIDE_PAR).index(t["valide_par"] or "moi"),
                                                 format_func=db.VALIDE_PAR.get)
                            if st.form_submit_button("Enregistrer", type="primary"):
                                db.update_tache(tid, {"titre": n_titre.strip() or t["titre"],
                                                      "description": n_desc, "priorite": n_prio,
                                                      "date_limite": n_date})
                                if n_statut != statut:
                                    db.set_tache_statut({**t, "titre": n_titre}, n_statut, n_par)
                                elif statut == "valide" and n_par != t["valide_par"]:
                                    db.update_tache(tid, {"valide_par": n_par})
                                ui.flash("Tâche modifiée.")
                                st.rerun()
                    with b4.popover("🗑", help="Supprimer"):
                        st.write("Supprimer définitivement cette tâche ?")
                        if st.button("Oui, supprimer", key=f"del_{tid}", type="primary"):
                            db.delete_tache(tid)
                            db.add_historique(cid, "tache", f"Tâche « {t['titre']} » supprimée.")
                            ui.flash("Tâche supprimée.", "🗑")
                            st.rerun()
                        if t["clickup_task_id"]:
                            st.caption("La tâche ClickUp liée n'est pas supprimée.")
                    # Lien ClickUp : ouvrir la tâche liée, ou l'envoyer (jamais deux fois)
                    if t["clickup_task_id"]:
                        st.markdown(f"[Ouvrir dans ClickUp ↗]({t['clickup_url']})")
                        if t["clickup_delie"]:
                            st.caption("⚠️ Déliée : introuvable dans la liste ClickUp.")
                    elif cu.configure():
                        if st.button("➡️ Envoyer vers ClickUp", key=f"cu_{tid}", width="stretch"):
                            try:
                                sync.envoyer_tache(t, sync.reglages()["mapping"])
                                ui.flash("Tâche créée dans ClickUp.")
                                st.rerun()
                            except cu.ClickUpError as e:
                                st.error(str(e))

# --- Argent ------------------------------------------------------------------
with t_argent:
    ui.kpis([
        ("Prix du site", db.fmt_euro(c["prix_site"]), ""),
        ("Acompte reçu", db.fmt_euro(c["acompte_recu"]), ""),
        ("Solde restant", db.fmt_euro(c["solde_restant"]), "rouge" if c["solde_restant"] > 0 else ""),
        ("Abonnement mensuel", db.fmt_euro(c["abonnement_mensuel"]), "accent"),
        ("Prochain paiement", fmt_date(c["date_prochain_paiement"]), ""),
    ])
    st.markdown(ui.voyant_html(alerts.voyant(al, "paiement"),
                               "Paiement à jour" if c["paiement_a_jour"] else "Paiement pas à jour"),
                unsafe_allow_html=True)
    for x in (x for x in al if x["categorie"] == "paiement"):
        st.markdown(ui.alerte_html(x), unsafe_allow_html=True)
    if c["abonnement_mensuel"] > 0:
        aide = "Avance la date du prochain paiement d'un mois et l'écrit dans l'historique."
    else:
        aide = "Sans abonnement : le solde restant est considéré comme encaissé."
    if st.button("💶 Marquer le paiement reçu", type="primary"):
        ui.flash(db.mark_payment_received(c))
        st.rerun()
    st.caption(aide)

    with st.expander("Modifier les montants"):
        with st.form(f"argent_{cid}"):
            a, b = st.columns(2)
            prix = a.number_input("Prix du site (€)", 0.0, step=50.0, value=float(c["prix_site"]))
            acompte = b.number_input("Acompte reçu (€)", 0.0, step=50.0, value=float(c["acompte_recu"]))
            solde = a.number_input("Solde restant (€)", 0.0, step=50.0, value=float(c["solde_restant"]),
                                   help="Laisse tel quel et coche la case ci-dessous pour le recalculer.")
            abo = b.number_input("Abonnement mensuel (€)", 0.0, step=1.0, value=float(c["abonnement_mensuel"]))
            dpp = a.date_input("Prochain paiement", c["date_prochain_paiement"], format="DD/MM/YYYY")
            a_jour = b.checkbox("Paiement à jour", value=c["paiement_a_jour"])
            recalc = st.checkbox("Recalculer le solde (prix − acompte)")
            if st.form_submit_button("Enregistrer", type="primary"):
                db.update_client(cid, {"prix_site": prix, "acompte_recu": acompte,
                                       "solde_restant": max(prix - acompte, 0.0) if recalc else solde,
                                       "abonnement_mensuel": abo, "date_prochain_paiement": dpp,
                                       "paiement_a_jour": a_jour})
                ui.flash("Montants enregistrés.")
                st.rerun()

# --- SEO ---------------------------------------------------------------------
with t_seo:
    audit = c["date_dernier_audit_seo"]
    ui.kpis([
        ("Dernier audit SEO", fmt_date(audit) + (f" ({(today - audit).days} j)" if audit else ""),
         "rouge" if alerts.voyant(al, "seo") != "ok" else "accent"),
        ("Statut SEO", db.SEO_STATUTS.get(c["seo_statut"], "—"), ""),
        ("Fiche Google", db.FICHE_GOOGLE_STATUTS.get(c["fiche_google_statut"], "—"), ""),
        ("Search Console", "Oui" if c["search_console"] else "Non", ""),
    ])
    for x in (x for x in al if x["categorie"] == "seo"):
        st.markdown(ui.alerte_html(x), unsafe_allow_html=True)
    with st.form(f"seo_{cid}"):
        a, b = st.columns(2)
        seo = a.selectbox("Statut SEO", list(db.SEO_STATUTS), format_func=db.SEO_STATUTS.get,
                          index=list(db.SEO_STATUTS).index(c["seo_statut"] or "a_faire"))
        fg = b.selectbox("Fiche Google", list(db.FICHE_GOOGLE_STATUTS),
                         format_func=db.FICHE_GOOGLE_STATUTS.get,
                         index=list(db.FICHE_GOOGLE_STATUTS).index(c["fiche_google_statut"] or "aucune"))
        n_audit = a.date_input("Date du dernier audit", audit, format="DD/MM/YYYY")
        sc = b.checkbox("Search Console branchée", value=c["search_console"])
        notes = st.text_area("Notes SEO", c["seo_notes"] or "")
        if st.form_submit_button("Enregistrer le SEO", type="primary"):
            db.update_client(cid, {"seo_statut": seo, "fiche_google_statut": fg,
                                   "date_dernier_audit_seo": n_audit, "search_console": sc,
                                   "seo_notes": notes})
            if n_audit and n_audit != audit:
                db.add_historique(cid, "seo", f"Audit SEO enregistré au {n_audit:%d/%m/%Y}.")
            else:
                db.add_historique(cid, "seo", "Informations SEO mises à jour.")
            ui.flash("SEO enregistré.")
            st.rerun()

# --- Technique ------------------------------------------------------------------
with t_tech:
    for x in (x for x in al if x["categorie"] == "echeances"):
        st.markdown(ui.alerte_html(x), unsafe_allow_html=True)
    with st.form(f"tech_{cid}"):
        a, b = st.columns(2)
        heb = a.text_input("Hébergeur", c["hebergeur"] or "")
        stack = b.text_input("Stack", c["stack"] or "")
        d_dom = a.date_input("Renouvellement domaine", c["date_renouvellement_domaine"], format="DD/MM/YYYY")
        d_heb = b.date_input("Renouvellement hébergement", c["date_renouvellement_hebergement"],
                             format="DD/MM/YYYY")
        acces = st.text_input("Où sont rangés les accès", c["emplacement_acces"] or "",
                              help="Indique l'emplacement (ex. gestionnaire de mots de passe, dossier X). "
                                   "Ne saisis jamais de mot de passe ici.")
        if st.form_submit_button("Enregistrer", type="primary"):
            db.update_client(cid, {"hebergeur": heb, "stack": stack,
                                   "date_renouvellement_domaine": d_dom,
                                   "date_renouvellement_hebergement": d_heb, "emplacement_acces": acces})
            db.add_historique(cid, "technique", "Informations techniques mises à jour.")
            ui.flash("Technique enregistrée.")
            st.rerun()

# --- Historique --------------------------------------------------------------
HISTO_EMOJI = {"note": "📝", "tache": "📌", "paiement": "💶", "validation": "✅",
               "technique": "🛠️", "seo": "🔎"}
with t_histo:
    with st.form(f"note_{cid}", clear_on_submit=True):
        note = st.text_area("Ajouter une note", height=80)
        if st.form_submit_button("Ajouter au fil", type="primary") and note.strip():
            db.add_historique(cid, "note", note.strip())
            ui.flash("Note ajoutée.")
            st.rerun()
    h = db.historique(cid)
    if not h:
        st.caption("Aucun événement pour l'instant.")
    for e in h:
        quand = e["date"].strftime("%d/%m/%Y %H:%M") if e["date"] else "—"
        st.markdown(f"{HISTO_EMOJI.get(e['type'], '•')} <span class='muted'>{quand} · "
                    f"{esc(db.HISTO_TYPES.get(e['type'], e['type']))}</span>  \n{esc(e['texte'])}",
                    unsafe_allow_html=True)

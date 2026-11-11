"""💬 Prospects DM : suivi des conversations Instagram (import auto) et TikTok (saisie manuelle)."""
from datetime import date, datetime

import streamlit as st

import db
import dm
import instagram_client as ig
import ui
from ui import esc, fmt_date

ui.entete("Prospection", "Prospects DM",
          "Les conversations Instagram et TikTok à suivre : qui attend une réponse, qui relancer, qui convertir.")

today = date.today()
tous = db.prospects()
ouverts = [p for p in tous if p["statut"] not in dm.FERMES]
repondre = [p for p in ouverts if dm.a_repondre(p)]
relances = [p for p in ouverts if dm.relance_due(p, today)]
convertis = [p for p in tous if p["statut"] == "converti"]

if repondre or relances:
    ui.bandeau("orange", f"{len(repondre)} conversation(s) attendent ta réponse, "
                         f"{len(relances)} relance(s) à faire aujourd'hui.")
elif tous:
    ui.bandeau("ok", "Tout le monde a sa réponse et aucune relance n'est due.")

ui.kpis([
    ("Conversations ouvertes", len(ouverts), "accent"),
    ("À répondre", len(repondre), "rouge" if repondre else ""),
    ("Relances dues", len(relances), "rouge" if relances else ""),
    ("Rendez-vous / devis", sum(p["statut"] in ("rdv", "devis") for p in tous), ""),
    ("Convertis en clients", len(convertis), ""),
    ("Taux de conversion", f"{round(100 * len(convertis) / len(tous))} %" if tous else "—", ""),
])

# --- Import Instagram ----------------------------------------------------------------
if ig.configure():
    c1, c2 = st.columns([1.2, 2], vertical_alignment="center")
    if c1.button("🔄 Importer Instagram", type="primary", width="stretch"):
        barre = st.progress(0.0, text="Lecture des conversations Instagram…")
        try:
            s = dm.importer_instagram(progression=lambda i, n: barre.progress(
                (i + 1) / max(n, 1), text=f"Conversation {i + 1} / {n}"))
            ui.flash(f"Instagram : {s['crees']} nouvelle(s) conversation(s), {s['mis_a_jour']} mise(s) à jour.")
            st.rerun()
        except ig.InstagramError as e:
            barre.empty()
            st.error(str(e))
    dernier = dm.dernier_import()
    c2.caption(f"Dernier import : {dernier:%d/%m à %H:%M}" if dernier else
               "Premier import : clique sur le bouton (environ 1 seconde par conversation). "
               "Ensuite, l'import se fait tout seul toutes les 15 minutes.")
else:
    st.info("**Instagram non relié.** Ajoute `INSTAGRAM_TOKEN` dans les secrets Streamlit pour "
            "importer tes DM automatiquement (voir le README). TikTok se suit à la main ci-dessous.")

# --- Ajout manuel ----------------------------------------------------------------------
with st.expander("➕ Ajouter un prospect (TikTok ou autre)"):
    with st.form("nouveau_prospect", clear_on_submit=True):
        a, b = st.columns(2)
        plateforme = a.selectbox("Plateforme", list(dm.PLATEFORMES), index=1, format_func=dm.PLATEFORMES.get)
        pseudo = b.text_input("Pseudo (sans @)")
        nom = a.text_input("Nom ou commerce")
        secteur = b.text_input("Secteur", placeholder="Restaurant, coiffeur…")
        statut = a.selectbox("Statut", list(dm.STATUTS), format_func=dm.STATUTS.get)
        relance = b.date_input("Prochaine relance", None, format="DD/MM/YYYY")
        de = st.radio("Dernier message envoyé par", ["eux", "moi"], horizontal=True,
                      format_func={"eux": "La personne", "moi": "Moi"}.get)
        notes = st.text_area("Notes", height=70)
        if st.form_submit_button("Ajouter", type="primary"):
            if not (pseudo.strip() or nom.strip()):
                st.error("Indique au moins un pseudo ou un nom.")
            else:
                db.create_prospect({
                    "plateforme": plateforme, "pseudo": pseudo.strip().lstrip("@"), "nom": nom.strip(),
                    "secteur": secteur.strip(), "statut": statut, "prochaine_relance": relance,
                    "notes": notes, "dernier_message_de": de, "dernier_message_le": datetime.now(),
                    "profil_url": dm.profil_url(plateforme, pseudo)})
                ui.flash("Prospect ajouté.")
                st.rerun()

if not tous:
    st.info("Aucun prospect pour l'instant.")
    st.stop()

# --- Filtres ---------------------------------------------------------------------------
f1, f2, f3 = st.columns([2, 2, 1.3], vertical_alignment="bottom")
choix_plat = f1.multiselect("Plateforme", list(dm.PLATEFORMES), format_func=dm.PLATEFORMES.get,
                            placeholder="Toutes")
choix_stat = f2.multiselect("Statut", list(dm.STATUTS), format_func=dm.STATUTS.get,
                            default=[s for s in dm.STATUTS if s not in dm.FERMES], placeholder="Tous")
seulement = f3.toggle("À traiter uniquement")

liste = [p for p in tous
         if (not choix_plat or p["plateforme"] in choix_plat)
         and (not choix_stat or p["statut"] in choix_stat)
         and (not seulement or dm.a_traiter(p, today))]
# À traiter d'abord, puis les plus récents
liste.sort(key=lambda p: (not dm.a_traiter(p, today),
                          -(p["dernier_message_le"].timestamp() if p["dernier_message_le"] else 0)))
st.caption(f"{len(liste)} prospect(s)")


def depuis(dt):
    if not dt:
        return ""
    j = (datetime.now() - dt).days
    return "aujourd'hui" if j <= 0 else ("hier" if j == 1 else f"il y a {j} j")


for p in liste:
    pid = p["id"]
    with st.container(border=True, key=f"carte_prospect_{pid}"):
        haut, actions = st.columns([3, 2], vertical_alignment="center")
        titre = esc(p["nom"] or f"@{p['pseudo']}")
        lien = (f' · <a href="{esc(p["profil_url"])}" target="_blank">@{esc(p["pseudo"])} ↗</a>'
                if p["profil_url"] and p["pseudo"] else "")
        badges = []
        if dm.a_repondre(p):
            badges.append(ui.voyant_html("rouge", "À répondre"))
        if dm.relance_due(p, today):
            badges.append(ui.voyant_html("orange", "Relance due"))
        dernier = (f"{'Toi' if p['dernier_message_de'] == 'moi' else 'Lui / elle'} · {depuis(p['dernier_message_le'])}"
                   if p["dernier_message_de"] else "")
        haut.markdown(
            f"{dm.ICONES.get(p['plateforme'], '💬')} **{titre}**{lien}  \n"
            f"<span class='badge'>{esc(dm.STATUTS.get(p['statut'], p['statut']))}</span> "
            f"<span class='muted'>{esc(p['secteur'] or '')}"
            f"{' · relance le ' + fmt_date(p['prochaine_relance']) if p['prochaine_relance'] else ''}</span>  \n"
            f"{' '.join(badges)}"
            f"<span class='muted'>{esc(dernier)}{' — « ' + esc(p['apercu']) + ' »' if p['apercu'] else ''}</span>",
            unsafe_allow_html=True)

        b1, b2, b3, b4 = actions.columns(4)
        if p["statut"] not in dm.FERMES and b1.button("↩︎", key=f"rel_{pid}", help=f"Relancé : relance dans {dm.DELAI_RELANCE} jours"):
            dm.marquer_relance(p)
            ui.flash("Relance notée.")
            st.rerun()
        with b2.popover("✏️", help="Modifier"):
            with st.form(f"edit_prospect_{pid}"):
                n_statut = st.selectbox("Statut", list(dm.STATUTS), index=list(dm.STATUTS).index(p["statut"]),
                                        format_func=dm.STATUTS.get)
                n_relance = st.date_input("Prochaine relance", p["prochaine_relance"], format="DD/MM/YYYY")
                n_nom = st.text_input("Nom ou commerce", p["nom"] or "")
                n_secteur = st.text_input("Secteur", p["secteur"] or "")
                n_de = st.radio("Dernier message envoyé par", ["eux", "moi"], horizontal=True,
                                index=0 if p["dernier_message_de"] != "moi" else 1,
                                format_func={"eux": "La personne", "moi": "Moi"}.get)
                n_notes = st.text_area("Notes", p["notes"] or "")
                if st.form_submit_button("Enregistrer", type="primary"):
                    db.update_prospect(pid, {"statut": n_statut, "prochaine_relance": n_relance,
                                             "nom": n_nom.strip(), "secteur": n_secteur.strip(),
                                             "dernier_message_de": n_de, "notes": n_notes})
                    ui.flash("Prospect mis à jour.")
                    st.rerun()
        if p["client_lie_id"] and db.client(p["client_lie_id"]):
            if b3.button("👤", key=f"fiche_{pid}", help="Ouvrir la fiche client"):
                st.session_state["client_id"] = p["client_lie_id"]
                st.switch_page("views/client.py")
        elif b3.button("➜👤", key=f"conv_{pid}", help="Convertir en client (crée la fiche)"):
            cid = dm.convertir_en_client(p)
            st.session_state["client_id"] = cid
            ui.flash("Fiche client créée.")
            st.switch_page("views/client.py")
        with b4.popover("🗑", help="Supprimer"):
            st.write("Supprimer ce prospect du suivi ? (rien n'est supprimé sur Instagram ou TikTok)")
            if p["ig_conversation_id"]:
                st.caption("Cette conversation ne sera plus importée depuis Instagram.")
            if st.button("Oui, supprimer", key=f"del_p_{pid}", type="primary"):
                dm.supprimer(p)
                ui.flash("Prospect supprimé.", "🗑")
                st.rerun()

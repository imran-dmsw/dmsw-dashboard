"""Point d'entrée du tableau de bord DMSW : thème, mot de passe, navigation.

Lancer :  streamlit run app.py
"""
import hmac
import os

import streamlit as st

import db
import sync
import ui

st.set_page_config(page_title="DMSW — Tableau de bord", page_icon="📊", layout="wide")
ui.inject_css()

# Mot de passe par défaut UNIQUEMENT en local (SQLite) quand rien n'est configuré.
MOT_DE_PASSE_LOCAL = "dmsw"


def est_local() -> bool:
    """Vrai si l'app est ouverte depuis cet ordinateur (localhost), jamais en ligne."""
    try:
        hote = (st.context.headers.get("Host") or "").split(":")[0]
    except Exception:
        return False
    return hote in ("localhost", "127.0.0.1", "[::1]")


def check_password() -> bool:
    """Écran de connexion. Rien d'autre n'est affiché tant qu'il n'est pas validé."""
    if st.session_state.get("auth_ok"):
        return True

    attendu = db.secret("APP_PASSWORD")
    if not attendu and db.mode() == "sqlite" and est_local():
        attendu = MOT_DE_PASSE_LOCAL

    _, centre, _ = st.columns([1, 2, 1])
    with centre:
        ui.logo("login")
        st.markdown("### Connexion")
        if not attendu:
            st.error("APP_PASSWORD n'est pas défini dans les secrets : accès bloqué.")
            st.stop()
        with st.form("login"):
            saisi = st.text_input("Mot de passe", type="password")
            ok = st.form_submit_button("Entrer", type="primary", width="stretch")
        if not db.secret("APP_PASSWORD"):
            st.caption(f"Mode local sans configuration : mot de passe « {MOT_DE_PASSE_LOCAL} ».")
        if ok:
            if hmac.compare_digest(saisi.encode(), str(attendu).encode()):
                st.session_state["auth_ok"] = True
                st.rerun()
            st.error("Mot de passe incorrect.")
    return False


if not check_password():
    st.stop()

# En ligne, la base de secours SQLite est effacée à chaque redémarrage de Streamlit Cloud :
# on refuse de démarrer plutôt que d'enregistrer des données qui disparaîtront.
# (DMSW_AUTORISER_SQLITE=1 : réservé aux tests automatiques.)
if db.mode() == "sqlite" and not est_local() and os.environ.get("DMSW_AUTORISER_SQLITE") != "1":
    ui.logo("login")
    st.error("**Supabase n'est pas branché : l'app est bloquée pour protéger tes données.**  \n"
             "Sans Supabase, tout ce qui est saisi en ligne serait effacé au prochain redémarrage.")
    st.markdown("Dans Streamlit Cloud → ⋮ → **Settings → Secrets**, vérifie ces deux lignes "
                "(noms exacts, guillemets compris) :")
    st.code('SUPABASE_URL = "https://xxxx.supabase.co"\nSUPABASE_KEY = "clé service_role"', language="toml")
    st.caption("L'URL doit être celle du projet Supabase où tu as lancé schema.sql "
               "(Supabase → Project Settings → API), sans « /rest/v1 » à la fin.")
    st.stop()

# --- Navigation ------------------------------------------------------------
PAGES = [
    st.Page("views/overview.py", title="Vue d'ensemble", icon="📊", default=True),
    st.Page("views/chiffres.py", title="Tableau de bord", icon="📈"),
    st.Page("views/today.py", title="Aujourd'hui", icon="✅"),
    st.Page("views/client.py", title="Fiche client", icon="👤"),
    st.Page("views/edit_client.py", title="Nouveau / Modifier", icon="➕"),
    st.Page("views/calendar.py", title="Calendrier", icon="📅"),
    st.Page("views/sprint.py", title="Sprint ClickUp", icon="🗂️"),
    st.Page("views/synchronisation.py", title="Synchronisation", icon="🔗"),
    st.Page("views/settings.py", title="Paramètres", icon="⚙️"),
]
page = st.navigation(PAGES, position="hidden")  # menu construit à la main sous le logo

with st.sidebar:
    ui.logo()
    for p in PAGES:
        st.page_link(p)
    st.divider()
    st.caption("Données : " + ("☁️ Supabase" if db.mode() == "supabase" else "💾 SQLite local"))
    if st.button("Se déconnecter", width="stretch"):
        st.session_state.clear()
        st.rerun()

# Synchro ClickUp automatique (si configurée, hors simulation, toutes les 5 minutes)
sync.synchro_auto()

ui.show_flash()
page.run()

"""Thème DMSW (clair, sobre et premium), CSS injecté et composants réutilisables."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

import db

# Palette : un seul accent bleu, fond clair, cartes blanches
BLEU = "#1a82d4"
BLEU_FONCE = "#0d1b2a"
FOND = "#f5f7fb"
BORDURE = "#e3eaf2"
TEXTE = "#0d1b2a"
GRIS = "#5b6b7f"
VERT, ORANGE, ROUGE = "#16a34a", "#f59e0b", "#dc2626"
COULEURS_VOYANT = {"ok": VERT, "orange": ORANGE, "rouge": ROUGE}
FONDS_VOYANT = {"ok": "#e8f7ee", "orange": "#fff5e1", "rouge": "#fdecec"}
EMOJI_VOYANT = {"ok": "🟢", "orange": "🟠", "rouge": "🔴"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* Police Inter partout, titres en 700, jamais de majuscules forcées */
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp div[data-testid="stMarkdownContainer"], .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
    font-family: 'Inter', sans-serif !important;
    text-transform: none !important;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-weight: 700 !important; color: {TEXTE}; letter-spacing: -0.02em; }}
.stApp {{ background: {FOND}; color: {TEXTE}; }}

/* Contenu centré, 1 120 px maximum */
.block-container {{ max-width: 1120px !important; padding-top: 3rem !important; margin: 0 auto; }}

/* Barre latérale en dégradé bleu nuit */
section[data-testid="stSidebar"] > div:first-child {{
    background: linear-gradient(180deg, {BLEU_FONCE} 0%, #12304d 100%);
}}
section[data-testid="stSidebar"] {{ border-right: none; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span,
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] .stCaption {{ color: #d6e2ef !important; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{ background: rgba(255,255,255,0.08); }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {{
    background: rgba(26,130,212,0.28);
}}
section[data-testid="stSidebar"] button {{
    background: rgba(255,255,255,0.06) !important; color: #fff !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
}}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12); }}

/* Logo texte */
.dmsw-logo {{ font-weight: 800; font-size: 1.9rem; color: #fff; letter-spacing: -0.03em; line-height: 1; }}
.dmsw-logo span {{ color: {BLEU}; }}
.dmsw-sub {{ color: #8fa6bf; font-size: 0.8rem; margin: 0.35rem 0 1rem 0; }}
.login .dmsw-logo {{ color: {TEXTE}; }}
.login .dmsw-sub {{ color: {GRIS}; }}

/* En-tête de page : pastille de rubrique, grand titre, phrase d'explication */
.entete {{ margin: 0 0 1.2rem 0; }}
.rubrique {{
    display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 0.78rem;
    font-weight: 600; color: {BLEU}; background: rgba(26,130,212,0.10); margin-bottom: 0.6rem;
}}
.entete h1 {{ font-size: 2.1rem !important; margin: 0 !important; padding: 0 !important; line-height: 1.15; }}
.entete p {{ color: {GRIS}; font-size: 1rem; margin: 0.4rem 0 0 0; }}
.entete a {{ color: {BLEU}; text-decoration: none; font-weight: 600; }}

/* Bandeau d'état coloré */
.bandeau {{
    border-radius: 16px; padding: 14px 18px; margin: 0 0 1.2rem 0; font-weight: 500;
    border: 1px solid; display: flex; gap: 10px; align-items: center;
}}

/* Cartes blanches arrondies, bordure claire, ombre douce */
.carte, .kpi, .stApp div[class*="st-key-carte"] {{
    background: #fff; border: 1px solid {BORDURE} !important; border-radius: 16px !important;
    box-shadow: 0 1px 2px rgba(13,27,42,0.04), 0 6px 20px rgba(13,27,42,0.05);
}}
.carte {{ padding: 18px 20px; margin-bottom: 1rem; }}
.carte h4 {{ margin: 0 0 0.9rem 0 !important; font-size: 1rem !important; }}

/* 6 indicateurs : 3 par ligne, 2 sur mobile */
.kpi-grid {{ display: grid; gap: 14px; margin: 0 0 1.4rem 0; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.kpi {{ padding: 16px 18px; min-width: 0; }}
.kpi .label {{ color: {GRIS}; font-size: 0.82rem; font-weight: 500; }}
.kpi .value {{
    font-weight: 700; font-size: 1.55rem; color: {TEXTE}; margin-top: 4px; letter-spacing: -0.02em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.kpi.accent .value {{ color: {BLEU}; }}
.kpi.rouge .value {{ color: {ROUGE}; }}

/* Barres horizontales de 10 px arrondies */
.barre-ligne {{ margin: 0 0 12px 0; }}
.barre-ligne .haut {{ display: flex; justify-content: space-between; font-size: 0.86rem; margin-bottom: 5px; }}
.barre-ligne .haut b {{ font-weight: 600; }}
.barre {{ height: 10px; border-radius: 999px; background: #edf1f7; overflow: hidden; }}
.barre > div {{ height: 10px; border-radius: 999px; }}

/* Pastilles, badges, alertes */
.pill {{
    display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; margin: 0 4px 4px 0;
    border-radius: 999px; font-size: 0.78rem; font-weight: 600; background: #fff;
    border: 1px solid {BORDURE}; color: {TEXTE}; white-space: nowrap;
}}
.dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
.badge {{
    display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem;
    font-weight: 600; background: rgba(26,130,212,0.10); color: {BLEU};
}}
.alerte {{
    border-left: 4px solid; padding: 9px 14px; margin: 6px 0; border-radius: 10px;
    background: #fff; font-size: 0.9rem; border-top: 1px solid {BORDURE};
    border-right: 1px solid {BORDURE}; border-bottom: 1px solid {BORDURE};
}}
.muted {{ color: {GRIS}; font-size: 0.85rem; }}

/* Bouton principal en dégradé bleu */
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"],
.stApp [data-testid="stBaseButton-primary"], .stApp [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: linear-gradient(135deg, #2b95e8 0%, {BLEU} 55%, #1269ad 100%) !important;
    border: none !important; color: #fff !important; font-weight: 600 !important;
    box-shadow: 0 4px 14px rgba(26,130,212,0.28);
}}
.stApp button[kind="primary"]:hover, .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    filter: brightness(1.06);
}}

/* Onglets */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}

/* Mobile */
@media (max-width: 640px) {{
    .block-container {{ padding: 3.6rem 0.9rem 3rem 0.9rem !important; }}
    .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .kpi .value {{ font-size: 1.2rem; }}
    .entete h1 {{ font-size: 1.6rem !important; }}
}}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def logo(classe: str = ""):
    st.markdown(f'<div class="{classe}"><div class="dmsw-logo">DMSW<span>.</span></div>'
                '<div class="dmsw-sub">Tableau de bord de l\'agence</div></div>',
                unsafe_allow_html=True)


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def entete(rubrique: str, titre: str, phrase: str = "", phrase_html: bool = False):
    """En-tête de page : pastille de rubrique, grand titre, phrase d'explication."""
    p = phrase if phrase_html else esc(phrase)
    st.markdown(f'<div class="entete"><span class="rubrique">{esc(rubrique)}</span>'
                f'<h1>{esc(titre)}</h1>{f"<p>{p}</p>" if p else ""}</div>',
                unsafe_allow_html=True)


def bandeau(niveau: str, texte: str):
    """Bandeau d'état coloré (ok / orange / rouge)."""
    st.markdown(f'<div class="bandeau" style="background:{FONDS_VOYANT[niveau]};'
                f'border-color:{COULEURS_VOYANT[niveau]}33;color:{TEXTE}">'
                f'<span class="dot" style="background:{COULEURS_VOYANT[niveau]};width:10px;height:10px">'
                f'</span>{esc(texte)}</div>', unsafe_allow_html=True)


def voyant_html(niveau: str, texte: str = "") -> str:
    """Pastille colorée (avec texte optionnel)."""
    label = texte or {"ok": "OK", "orange": "À surveiller", "rouge": "Urgent"}[niveau]
    return (f'<span class="pill"><span class="dot" style="background:{COULEURS_VOYANT[niveau]}">'
            f'</span>{esc(label)}</span>')


def kpis(items: list):
    """items = [(libellé, valeur, classe css)] — grille 3 par ligne (2 sur mobile)."""
    cards = "".join(
        f'<div class="kpi {cls}"><div class="label">{esc(lbl)}</div>'
        f'<div class="value" title="{esc(val)}">{esc(val)}</div></div>'
        for lbl, val, cls in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def carte_barres(titre: str, items: list, maximum: float | None = None, suffixe: str = "",
                 formateur=None):
    """Carte à barres horizontales. items = [(libellé, valeur, couleur)].
    formateur : fonction d'affichage de la valeur (ex. db.fmt_euro)."""
    maxi = maximum or max([v for _, v, _ in items] + [1])
    lignes = "".join(
        f'<div class="barre-ligne"><div class="haut"><span>{esc(lbl)}</span><b>{esc(formateur(v) if formateur else v)}{suffixe}</b></div>'
        f'<div class="barre"><div style="width:{min(v / maxi, 1) * 100:.0f}%;background:{coul}"></div></div></div>'
        for lbl, v, coul in items
    )
    st.markdown(f'<div class="carte"><h4>{esc(titre)}</h4>{lignes}</div>', unsafe_allow_html=True)


def alerte_html(a: dict, avec_client: bool = False) -> str:
    qui = f"<b>{esc(a['client_nom'])}</b> — " if avec_client else ""
    return (f'<div class="alerte" style="border-left-color:{COULEURS_VOYANT[a["niveau"]]}">'
            f'{EMOJI_VOYANT[a["niveau"]]} {qui}{esc(a["message"])}</div>')


# --- Messages qui survivent à un st.rerun() --------------------------------
def flash(msg: str, icon: str = "✅"):
    st.session_state["_flash"] = (msg, icon)


def show_flash():
    if "_flash" in st.session_state:
        msg, icon = st.session_state.pop("_flash")
        st.toast(msg, icon=icon)


# --- Sélection d'un client partagée entre les pages -----------------------
def client_selector(label: str = "Client", key: str = "client_select", inclure_archives=True):
    """Selectbox de clients, synchronisée avec st.session_state['client_id']."""
    liste = [c for c in db.clients() if inclure_archives or c["statut_projet"] != "archive"]
    if not liste:
        return None
    ids = [c["id"] for c in liste]
    noms = {c["id"]: c["nom"] for c in liste}
    courant = st.session_state.get("client_id")
    index = ids.index(courant) if courant in ids else 0
    choix = st.selectbox(label, ids, index=index, format_func=noms.get, key=f"{key}_{courant}")
    st.session_state["client_id"] = choix
    return db.client(choix)


def prochaine_action(taches: list):
    """Prochaine tâche non validée : date limite la plus proche, puis priorité."""
    ordre_prio = {"urgente": 0, "haute": 1, "normale": 2, "basse": 3}
    ouvertes = [t for t in taches if t["statut"] != "valide"]
    if not ouvertes:
        return None
    return min(ouvertes, key=lambda t: (t["date_limite"] or date.max,
                                         ordre_prio.get(t["priorite"], 2)))


# --- ClickUp -----------------------------------------------------------------
def clickup_non_configure():
    """Message propre quand le token ClickUp est absent (l'app marche sans)."""
    st.info("**Intégration ClickUp non configurée.** Ajoute `CLICKUP_TOKEN` et `CLICKUP_LIST_ID` "
            "dans les secrets Streamlit pour activer cette section (voir le README).")


def taches_sprint():
    """Tâches du sprint ClickUp (en cache), ou (None, message d'erreur)."""
    import clickup_client as cu
    if not cu.configure():
        return None, None
    try:
        return cu.taches_liste(cu.list_id(), True), None
    except cu.ClickUpError as e:
        return None, str(e)


def indicateur_sprint():
    """Pastille en haut de l'accueil : tâches du sprint ClickUp en retard."""
    import clickup_client as cu
    taches, erreur = taches_sprint()
    if taches is None:
        if erreur:
            st.markdown(f'<span class="pill">🗂️ Sprint ClickUp : {esc(erreur)}</span>', unsafe_allow_html=True)
        return
    n = sum(cu.en_retard(t) for t in taches)
    niveau = "rouge" if n else "ok"
    st.markdown(voyant_html(niveau, f"🗂️ Sprint ClickUp : {n} tâche(s) en retard"),
                unsafe_allow_html=True)

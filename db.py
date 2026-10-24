"""Couche d'accès aux données du tableau de bord DMSW.

Deux moteurs, une seule interface :
- Supabase (Postgres) si SUPABASE_URL et SUPABASE_KEY sont présents dans st.secrets ;
- SQLite (fichier data/dmsw.db) sinon, pour tester en local sans configuration.

Le reste de l'application n'utilise que les fonctions publiques de ce fichier
(clients(), taches(), create_client(), set_tache_statut(), ...).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from dateutil import parser as dtparser
from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Modèle de données : type logique de chaque colonne (hors "id").
# Sert à créer les tables SQLite, à convertir les valeurs et à importer les CSV.
# ---------------------------------------------------------------------------
CLIENT_FIELDS = {
    # Identité
    "nom": "text", "activite": "text", "site_url": "text", "domaine": "text",
    "contact_nom": "text", "contact_tel": "text", "contact_email": "text",
    "date_livraison": "date", "statut_projet": "text", "notes": "text",
    # Argent
    "prix_site": "float", "acompte_recu": "float", "solde_restant": "float",
    "abonnement_mensuel": "float", "date_prochain_paiement": "date", "paiement_a_jour": "bool",
    # Technique
    "hebergeur": "text", "date_renouvellement_domaine": "date",
    "date_renouvellement_hebergement": "date", "stack": "text", "emplacement_acces": "text",
    # SEO
    "seo_statut": "text", "fiche_google_statut": "text", "search_console": "bool",
    "date_dernier_audit_seo": "date", "seo_notes": "text",
    # Sécurité
    "https_actif": "bool", "date_derniere_sauvegarde": "date",
    "date_derniere_mise_a_jour": "date", "double_auth": "bool", "securite_notes": "text",
    # Suivi
    "corrections_incluses": "int", "corrections_utilisees": "int", "created_at": "timestamp",
    # Client technique « DMSW (interne) » : exclu des revenus et des alertes
    "interne": "bool",
}
TACHE_FIELDS = {
    "client_id": "int", "titre": "text", "description": "text", "statut": "text",
    "priorite": "text", "date_limite": "date", "valide_par": "text",
    "date_validation": "date", "created_at": "timestamp",
    # Lien ClickUp
    "clickup_task_id": "text", "clickup_url": "text", "clickup_updated_at": "timestamp",
    "clickup_delie": "bool", "updated_at": "timestamp",
}
HISTORIQUE_FIELDS = {"client_id": "int", "date": "timestamp", "type": "text", "texte": "text"}
# Table technique (clé / valeur) : seuils d'alertes et réglages ClickUp.
PARAMETRES_FIELDS = {"cle": "text", "valeur": "text"}
# Journal de synchronisation ClickUp
SYNC_LOG_FIELDS = {
    "date": "timestamp", "direction": "text", "tache_id": "int", "champ": "text",
    "ancienne_valeur": "text", "nouvelle_valeur": "text", "resultat": "text",
}

TABLES = {
    "clients": CLIENT_FIELDS,
    "taches": TACHE_FIELDS,
    "historique": HISTORIQUE_FIELDS,
    "parametres": PARAMETRES_FIELDS,
    "sync_log": SYNC_LOG_FIELDS,
}
NOM_CLIENT_INTERNE = "DMSW (interne)"

# Valeurs possibles des listes déroulantes (valeur stockée -> libellé affiché)
STATUTS_PROJET = {"prospect": "Prospect", "en_cours": "En cours", "livre": "Livré",
                  "maintenance": "Maintenance", "archive": "Archivé"}
SEO_STATUTS = {"a_faire": "À faire", "en_cours": "En cours", "bon": "Bon"}
FICHE_GOOGLE_STATUTS = {"aucune": "Aucune", "a_creer": "À créer", "en_cours": "En cours",
                        "optimisee": "Optimisée"}
TACHE_STATUTS = {"a_faire": "À faire", "en_cours": "En cours", "valide": "Validé"}
PRIORITES = {"basse": "Basse", "normale": "Normale", "haute": "Haute", "urgente": "Urgente"}
VALIDE_PAR = {"moi": "Moi", "client": "Client"}
HISTO_TYPES = {"note": "Note", "tache": "Tâche", "paiement": "Paiement",
               "validation": "Validation", "technique": "Technique", "seo": "SEO"}

CLIENT_DEFAULTS = {
    "statut_projet": "prospect", "prix_site": 0.0, "acompte_recu": 0.0, "solde_restant": 0.0,
    "abonnement_mensuel": 0.0, "paiement_a_jour": True, "seo_statut": "a_faire",
    "fiche_google_statut": "aucune", "search_console": False, "https_actif": False,
    "double_auth": False, "corrections_incluses": 2, "corrections_utilisees": 0,
}

# Seuils d'alertes par défaut (modifiables dans Paramètres)
DEFAULT_PARAMETRES = {
    "solde_jours_apres_livraison": 15,
    "renouvellement_orange_jours": 30,
    "renouvellement_rouge_jours": 7,
    "audit_seo_jours": 90,
    "sauvegarde_jours": 60,
    "taches_horizon_jours": 7,
    "tarif_horaire": 20,
}

DEMO_PREFIX = "[Démo] "


# ---------------------------------------------------------------------------
# Lecture des secrets (st.secrets, puis variables d'environnement)
# ---------------------------------------------------------------------------
def secret(name: str, default=None):
    """Lit une clé dans st.secrets sans planter s'il n'y a pas de secrets.toml."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


def mode() -> str:
    """'supabase' si les clés sont configurées, sinon 'sqlite'."""
    return "supabase" if secret("SUPABASE_URL") and secret("SUPABASE_KEY") else "sqlite"


# ---------------------------------------------------------------------------
# Conversions de valeurs
# ---------------------------------------------------------------------------
def to_date(v):
    """Convertit une chaîne / datetime en date (None si vide ou invalide)."""
    if v is None or v == "" or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        s = str(v).strip()
        # ISO (2026-10-24) en priorité, sinon format français (24/10/2026)
        return dtparser.parse(s, dayfirst="/" in s).date()
    except (ValueError, OverflowError):
        return None


def _to_datetime(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = dtparser.isoparse(str(v))
        except ValueError:
            return None
    # Heure locale sans fuseau, pour pouvoir trier/comparer partout pareil
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def to_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "vrai", "oui", "yes", "x")
    return bool(v) if v is not None and v == v else False


def _from_db(table: str, row: dict) -> dict:
    """Valeurs brutes du moteur -> types Python (date, bool, float...)."""
    out = {"id": row.get("id")}
    for col, typ in TABLES[table].items():
        v = row.get(col)
        if typ == "date":
            v = to_date(v)
        elif typ == "timestamp":
            v = _to_datetime(v)
        elif typ == "bool":
            v = to_bool(v) if v is not None else False
        elif typ == "float":
            v = float(v) if v not in (None, "") else 0.0
        elif typ == "int":
            v = int(v) if v not in (None, "") else (None if col in ("client_id", "tache_id") else 0)
        out[col] = v
    return out


def _to_db(table: str, data: dict, sqlite: bool) -> dict:
    """Types Python -> valeurs acceptées par le moteur (ISO pour les dates)."""
    fields = TABLES[table]
    out = {}
    for col, v in data.items():
        if col not in fields:
            continue  # on ignore les clés inconnues (id, colonnes calculées...)
        typ = fields[col]
        if typ in ("date", "timestamp"):
            if v in ("", None):
                v = None
            elif isinstance(v, datetime):
                # Fuseau explicite : Postgres ne confond plus heure locale et UTC
                v = (v.astimezone() if v.tzinfo is None else v).isoformat()
            elif isinstance(v, date):
                v = v.isoformat()
        elif typ == "bool":
            v = to_bool(v)
            if sqlite:
                v = int(v)
        elif typ == "text" and v is not None:
            v = str(v)
        out[col] = v
    return out


# ---------------------------------------------------------------------------
# Moteurs de stockage (même interface : select / insert / update / delete)
# ---------------------------------------------------------------------------
_SQL_TYPES = {"text": "TEXT", "float": "REAL", "int": "INTEGER", "bool": "INTEGER",
              "date": "TEXT", "timestamp": "TEXT"}


class SQLiteBackend:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            for table, fields in TABLES.items():
                cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
                for col, typ in fields.items():
                    if col == "client_id":
                        cols.append("client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE")
                    else:
                        cols.append(f"{col} {_SQL_TYPES[typ]}")
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)})")
                # Migration : ajoute les colonnes manquantes sans toucher aux données
                existantes = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for col, typ in fields.items():
                    if col not in existantes:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {_SQL_TYPES[typ]}")
            # Une tâche ClickUp ne peut être liée qu'à une seule tâche locale
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS taches_clickup_idx "
                         "ON taches(clickup_task_id)")

    def select(self, table):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]

    def insert(self, table, row):
        cols = list(row)
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
            return cur.lastrowid

    def update(self, table, row_id, row):
        if not row:
            return
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in row)} WHERE id = ?",
                [*row.values(), row_id],
            )

    def delete(self, table, row_id):
        with self._conn() as conn:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", [row_id])


class SupabaseBackend:
    # Tables préfixées « dmsw_ » : le projet Supabase peut être partagé avec un autre
    # projet sans risque de collision (ex. une autre table « clients »).
    PREFIXE = "dmsw_"

    def __init__(self, url: str, key: str):
        from supabase import create_client  # import tardif : inutile en mode SQLite
        self.client = create_client(url, key)

    def _t(self, table):
        return self.client.table(self.PREFIXE + table)

    def select(self, table):
        # Petit volume (agence solo) : on charge la table entière, par pages de 1000
        rows, start = [], 0
        while True:
            batch = (self._t(table).select("*").order("id")
                     .range(start, start + 999).execute().data)
            rows.extend(batch)
            if len(batch) < 1000:
                return rows
            start += 1000

    def insert(self, table, row):
        return self._t(table).insert(row).execute().data[0]["id"]

    def update(self, table, row_id, row):
        if row:
            self._t(table).update(row).eq("id", row_id).execute()

    def delete(self, table, row_id):
        self._t(table).delete().eq("id", row_id).execute()


@st.cache_resource(show_spinner=False)
def get_backend():
    if mode() == "supabase":
        return SupabaseBackend(secret("SUPABASE_URL"), secret("SUPABASE_KEY"))
    # DMSW_DB_PATH : permet aux tests d'utiliser une base jetable
    chemin = os.environ.get("DMSW_DB_PATH") or Path(__file__).parent / "data" / "dmsw.db"
    return SQLiteBackend(Path(chemin))


# ---------------------------------------------------------------------------
# Lecture (mise en cache, vidée à chaque écriture)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def _load(table: str) -> list:
    return [_from_db(table, r) for r in get_backend().select(table)]


def _insert(table, data) -> int:
    row_id = get_backend().insert(table, _to_db(table, data, mode() == "sqlite"))
    _load.clear()
    return row_id


def _update(table, row_id, data):
    get_backend().update(table, row_id, _to_db(table, data, mode() == "sqlite"))
    _load.clear()


def _delete(table, row_id):
    get_backend().delete(table, row_id)
    _load.clear()


def raw_rows(table: str) -> list:
    """Lignes d'une table, pour l'export CSV."""
    return _load(table)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
def clients() -> list:
    return sorted(_load("clients"), key=lambda c: (c["nom"] or "").lower())


def client(client_id) -> dict | None:
    return next((c for c in _load("clients") if c["id"] == client_id), None)


def create_client(data: dict) -> int:
    row = {**CLIENT_DEFAULTS, **{k: v for k, v in data.items() if v is not None}}
    row["created_at"] = datetime.now()
    client_id = _insert("clients", row)
    add_historique(client_id, "note", "Fiche client créée.")
    return client_id


def update_client(client_id, data: dict):
    _update("clients", client_id, data)


def delete_client(client_id):
    _delete("clients", client_id)


# ---------------------------------------------------------------------------
# Tâches
# ---------------------------------------------------------------------------
def taches(client_id=None) -> list:
    rows = _load("taches")
    if client_id is not None:
        rows = [t for t in rows if t["client_id"] == client_id]
    return rows


def tache(tache_id) -> dict | None:
    return next((t for t in _load("taches") if t["id"] == tache_id), None)


def create_tache(data: dict) -> int:
    now = datetime.now()
    row = {"statut": "a_faire", "priorite": "normale", "updated_at": now, **data, "created_at": now}
    return _insert("taches", row)


def update_tache(tache_id, data: dict, touch: bool = True):
    """Met à jour une tâche. touch=True : updated_at = maintenant (modification locale).
    La synchro ClickUp passe touch=False pour fixer elle-même updated_at."""
    if touch:
        data = {**data, "updated_at": datetime.now()}
    _update("taches", tache_id, data)


def delete_tache(tache_id):
    _delete("taches", tache_id)


def set_tache_statut(tache: dict, statut: str, valide_par: str = "moi"):
    """Change le statut d'une tâche et l'écrit dans l'historique du client."""
    if tache["statut"] == statut:
        return
    data = {"statut": statut}
    if statut == "valide":
        data.update(date_validation=date.today(), valide_par=valide_par)
        texte = f"Tâche « {tache['titre']} » validée par {VALIDE_PAR.get(valide_par, valide_par).lower()}."
        typ = "validation"
    else:
        data.update(date_validation=None, valide_par=None)
        texte = (f"Tâche « {tache['titre']} » : {TACHE_STATUTS[tache['statut']]} → "
                 f"{TACHE_STATUTS[statut]}.")
        typ = "tache"
    update_tache(tache["id"], data)
    add_historique(tache["client_id"], typ, texte)


# ---------------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------------
def historique(client_id=None) -> list:
    rows = _load("historique")
    if client_id is not None:
        rows = [h for h in rows if h["client_id"] == client_id]
    return sorted(rows, key=lambda h: (h["date"] or datetime.min, h["id"]), reverse=True)


def add_historique(client_id, typ: str, texte: str, quand: datetime | None = None):
    _insert("historique", {"client_id": client_id, "type": typ, "texte": texte,
                           "date": quand or datetime.now()})


# ---------------------------------------------------------------------------
# Argent
# ---------------------------------------------------------------------------
def mark_payment_received(c: dict) -> str:
    """Bouton « Marquer le paiement reçu ».

    - Abonnement > 0 : la date du prochain paiement avance d'un mois.
    - Sans abonnement : le solde restant est considéré comme encaissé.
    Dans les deux cas : paiement à jour + ligne dans l'historique.
    Retourne le message affiché à l'utilisateur.
    """
    data = {"paiement_a_jour": True}
    if c["abonnement_mensuel"] > 0:
        base = c["date_prochain_paiement"] or date.today()
        nouvelle = base + relativedelta(months=1)
        data["date_prochain_paiement"] = nouvelle
        texte = (f"Paiement d'abonnement reçu ({fmt_euro(c['abonnement_mensuel'])}). "
                 f"Prochain paiement le {nouvelle:%d/%m/%Y}.")
    elif c["solde_restant"] > 0:
        data.update(acompte_recu=c["acompte_recu"] + c["solde_restant"], solde_restant=0.0)
        texte = f"Solde reçu ({fmt_euro(c['solde_restant'])}). Projet entièrement payé."
    else:
        texte = "Paiement marqué reçu (rien ne restait à encaisser)."
    update_client(c["id"], data)
    add_historique(c["id"], "paiement", texte)
    return texte


def fmt_euro(x) -> str:
    """1234.5 -> '1 234,50 €'."""
    s = f"{(x or 0):,.2f}".replace(",", "\u202f").replace(".", ",")
    return f"{s}\u00a0€"  # espaces insécables : le montant ne se coupe jamais


# ---------------------------------------------------------------------------
# Paramètres (seuils d'alertes)
# ---------------------------------------------------------------------------
def parametres() -> dict:
    p = dict(DEFAULT_PARAMETRES)
    for row in _load("parametres"):
        if row["cle"] in p:
            try:
                p[row["cle"]] = int(float(row["valeur"]))
            except (TypeError, ValueError):
                pass
    return p


def set_parametres(values: dict):
    existing = {r["cle"]: r["id"] for r in _load("parametres")}
    for cle, valeur in values.items():
        if cle in existing:
            _update("parametres", existing[cle], {"valeur": str(valeur)})
        else:
            _insert("parametres", {"cle": cle, "valeur": str(valeur)})


# ---------------------------------------------------------------------------
# Réglages texte (ClickUp : mapping des statuts, options, date de synchro)
# ---------------------------------------------------------------------------
def reglage(cle: str, defaut: str = "") -> str:
    row = next((r for r in _load("parametres") if r["cle"] == cle), None)
    return row["valeur"] if row and row["valeur"] is not None else defaut


def set_reglages(values: dict):
    """Comme set_parametres, pour des valeurs texte quelconques."""
    set_parametres({k: "" if v is None else v for k, v in values.items()})


# ---------------------------------------------------------------------------
# Client interne « DMSW (interne) » (tâches nées dans ClickUp)
# ---------------------------------------------------------------------------
def client_interne_id() -> int:
    """Identifiant du client interne, créé à la première utilisation."""
    existant = next((c for c in _load("clients") if c["interne"]), None)
    if existant:
        return existant["id"]
    return create_client({
        "nom": NOM_CLIENT_INTERNE, "activite": "Tâches internes de l'agence",
        "statut_projet": "en_cours", "interne": True, "paiement_a_jour": True,
        "corrections_incluses": 0, "seo_statut": "bon", "https_actif": True, "double_auth": True,
    })


# ---------------------------------------------------------------------------
# Journal de synchronisation
# ---------------------------------------------------------------------------
def add_sync_log(direction: str, tache_id, champ: str, avant, apres, resultat: str):
    _insert("sync_log", {
        "date": datetime.now(), "direction": direction, "tache_id": tache_id, "champ": champ,
        "ancienne_valeur": "" if avant is None else str(avant),
        "nouvelle_valeur": "" if apres is None else str(apres), "resultat": resultat,
    })


def update_sync_log(log_id, data: dict):
    _update("sync_log", log_id, data)


def sync_log(limite: int | None = None) -> list:
    rows = sorted(_load("sync_log"), key=lambda r: (r["date"] or datetime.min, r["id"]), reverse=True)
    return rows[:limite] if limite else rows

"""Import CSV : clients, tâches et historique (fichiers séparés ou un .zip).

- clients.csv : colonnes du modèle (nom obligatoire).
- taches.csv : client_nom + colonnes du modèle des tâches (titre obligatoire).
- historique.csv : client_nom, date, type, texte.

Rejouer l'import ne crée pas de doublon : un client déjà présent (même nom) est
ignoré, ainsi qu'une tâche (même client + titre) ou une ligne d'historique
(même client + date + texte) déjà présente.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, time

import pandas as pd

import db

FICHIERS = ("clients", "taches", "historique")


def lire_csv(contenu: bytes) -> pd.DataFrame:
    """CSV (séparateur deviné, BOM accepté) -> DataFrame de textes, sans NaN."""
    df = pd.read_csv(io.BytesIO(contenu), sep=None, engine="python", dtype=str,
                     encoding="utf-8-sig").fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df


def lire_fichiers(fichiers: list) -> dict:
    """Fichiers déposés (.csv ou .zip) -> {'clients': df, 'taches': df, 'historique': df}.
    Chaque fichier est reconnu par son nom (clients.csv, taches.csv, historique.csv)."""
    out = {}
    for nom, contenu in fichiers:
        if nom.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(contenu)) as z:
                for membre in z.namelist():
                    base = membre.rsplit("/", 1)[-1].lower()
                    if base.endswith(".csv") and base[:-4] in FICHIERS:
                        out[base[:-4]] = lire_csv(z.read(membre))
        elif nom.lower().endswith(".csv"):
            base = nom.rsplit("/", 1)[-1].lower()[:-4]
            # Un CSV au nom inconnu est traité comme une liste de clients (ancien comportement)
            out[base if base in FICHIERS else "clients"] = lire_csv(contenu)
    return out


def _convertir(v: str, typ: str, col: str):
    """Valeur texte -> valeur typée. Lève ValueError avec un message lisible."""
    v = v.strip()
    if typ == "date":
        d = db.to_date(v)
        if d is None:
            raise ValueError(f"date invalide en « {col} » ({v})")
        return d
    if typ == "float":
        try:
            return float(v.replace(" ", "").replace(" ", "").replace(",", ".").replace("€", ""))
        except ValueError:
            raise ValueError(f"nombre invalide en « {col} » ({v})") from None
    if typ == "int":
        try:
            return int(float(v.replace(",", ".")))
        except ValueError:
            raise ValueError(f"entier invalide en « {col} » ({v})") from None
    if typ == "bool":
        return db.to_bool(v)
    return v


def _ligne(row: dict, champs: dict, choix: dict) -> dict:
    """Une ligne CSV -> dictionnaire typé (colonnes inconnues ou vides ignorées)."""
    data = {}
    for col, v in row.items():
        if col in champs and v.strip() != "":
            data[col] = _convertir(v, champs[col], col)
    for champ, valeurs in choix.items():
        if champ in data and data[champ] not in valeurs:
            raise ValueError(f"valeur inconnue en « {champ} » ({data[champ]})")
    return data


CHAMPS_CLIENT = {k: v for k, v in db.CLIENT_FIELDS.items() if k not in ("created_at", "interne")}
CHAMPS_TACHE = {k: v for k, v in db.TACHE_FIELDS.items()
                if k in ("titre", "description", "statut", "priorite", "date_limite", "valide_par",
                         "date_validation")}
CHOIX_CLIENT = {"statut_projet": db.STATUTS_PROJET, "seo_statut": db.SEO_STATUTS,
                "fiche_google_statut": db.FICHE_GOOGLE_STATUTS}
CHOIX_TACHE = {"statut": db.TACHE_STATUTS, "priorite": db.PRIORITES, "valide_par": db.VALIDE_PAR}


def importer(tables: dict, simulation: bool = False) -> dict:
    """Importe les tables lues. En simulation, ne fait que compter.
    Renvoie {'crees': {...}, 'ignores': [...], 'erreurs': [...]}."""
    rapport = {"crees": {"clients": 0, "taches": 0, "historique": 0}, "ignores": [], "erreurs": []}
    par_nom = {(c["nom"] or "").strip().lower(): c["id"] for c in db.clients()}
    simules = set()  # noms des clients qui seraient créés (simulation)

    # 1. Clients
    for i, row in enumerate(tables.get("clients", pd.DataFrame()).to_dict("records")):
        try:
            data = _ligne(row, CHAMPS_CLIENT, CHOIX_CLIENT)
        except ValueError as e:
            rapport["erreurs"].append(f"clients.csv ligne {i + 2} : {e}")
            continue
        nom = (data.get("nom") or "").strip()
        if not nom:
            rapport["erreurs"].append(f"clients.csv ligne {i + 2} : nom manquant")
            continue
        if nom.lower() in par_nom or nom.lower() in simules:
            rapport["ignores"].append(f"Client « {nom} » déjà présent")
            continue
        if "solde_restant" not in data and "prix_site" in data:
            data["solde_restant"] = max(data["prix_site"] - data.get("acompte_recu", 0), 0)
        if nom.lower() == db.NOM_CLIENT_INTERNE.lower():
            data["interne"] = True  # devient le client interne de l'agence
        if simulation:
            simules.add(nom.lower())
        else:
            par_nom[nom.lower()] = db.create_client(data)
        rapport["crees"]["clients"] += 1

    def client_id(row, fichier, i):
        nom = (row.get("client_nom") or "").strip().lower()
        if nom in par_nom or nom in simules:
            return par_nom.get(nom, -1)
        rapport["erreurs"].append(f"{fichier} ligne {i + 2} : client « {row.get('client_nom')} » introuvable")
        return None

    # 2. Tâches
    existantes = {(t["client_id"], (t["titre"] or "").strip().lower()) for t in db.taches()}
    for i, row in enumerate(tables.get("taches", pd.DataFrame()).to_dict("records")):
        cid = client_id(row, "taches.csv", i)
        if cid is None:
            continue
        try:
            data = _ligne(row, CHAMPS_TACHE, CHOIX_TACHE)
        except ValueError as e:
            rapport["erreurs"].append(f"taches.csv ligne {i + 2} : {e}")
            continue
        titre = (data.get("titre") or "").strip()
        if not titre:
            rapport["erreurs"].append(f"taches.csv ligne {i + 2} : titre manquant")
            continue
        if (cid, titre.lower()) in existantes:
            rapport["ignores"].append(f"Tâche « {titre} » déjà présente")
            continue
        existantes.add((cid, titre.lower()))
        if not simulation:
            db.create_tache({**data, "client_id": cid})
        rapport["crees"]["taches"] += 1

    # 3. Historique
    deja = {(h["client_id"], h["date"].date() if h["date"] else None, (h["texte"] or "").strip())
            for h in db.historique()}
    for i, row in enumerate(tables.get("historique", pd.DataFrame()).to_dict("records")):
        cid = client_id(row, "historique.csv", i)
        if cid is None:
            continue
        texte = (row.get("texte") or "").strip()
        typ = (row.get("type") or "note").strip()
        d = db.to_date(row.get("date"))
        if not texte or typ not in db.HISTO_TYPES:
            rapport["erreurs"].append(f"historique.csv ligne {i + 2} : texte vide ou type inconnu ({typ})")
            continue
        if (cid, d, texte) in deja:
            rapport["ignores"].append(f"Historique « {texte[:40]}… » déjà présent")
            continue
        deja.add((cid, d, texte))
        if not simulation:
            quand = datetime.combine(d, time(12, 0)) if d else None
            db.add_historique(cid, typ, texte, quand)
        rapport["crees"]["historique"] += 1
    return rapport

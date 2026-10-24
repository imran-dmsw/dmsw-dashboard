"""Synchronisation dans les deux sens entre les tâches du dashboard et ClickUp.

Streamlit ne reçoit pas de webhooks : la synchro se fait par interrogation
(au chargement si la dernière date de plus de 5 minutes, ou via un bouton).

Fonctionnement en deux temps :
1. planifier() compare les deux côtés et renvoie une liste d'actions (fonction pure,
   sans aucun appel réseau ni écriture : c'est ce que montre le mode simulation) ;
2. appliquer() exécute ces actions, écrit sync_log et l'historique des clients.

Règles : seules les tâches liées (clickup_task_id) sont synchronisées, champ par champ,
la modification la plus récente gagne ; jamais de suppression automatique.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import clickup_client as cu
import db

# --- Correspondances ---------------------------------------------------------
PRIO_VERS_CLICKUP = {"urgente": 1, "haute": 2, "normale": 3, "basse": 4}
PRIO_DEPUIS_CLICKUP = {v: k for k, v in PRIO_VERS_CLICKUP.items()}
CHAMPS = ("titre", "statut", "priorite", "date_limite")
LIBELLES_CHAMPS = {"titre": "Titre", "statut": "Statut", "priorite": "Priorité",
                   "date_limite": "Date limite"}
ECART_CONFLIT = timedelta(minutes=2)
INTERVALLE_AUTO = timedelta(minutes=5)

# Réglages stockés dans la table parametres
R_MAP = {"a_faire": "clickup_statut_a_faire", "en_cours": "clickup_statut_en_cours",
         "valide": "clickup_statut_valide"}
R_SIMULATION = "clickup_simulation"      # "1" par défaut : la 1re synchro est simulée
R_AUTO_ENVOI = "clickup_auto_envoi"      # "0" par défaut
R_IMPORT = "clickup_import"              # "1" par défaut
R_DERNIERE = "clickup_derniere_synchro"  # ISO


def reglages() -> dict:
    mapping = {k: db.reglage(cle) for k, cle in R_MAP.items()}
    return {
        "mapping": mapping if all(mapping.values()) else None,
        "simulation": db.reglage(R_SIMULATION, "1") == "1",
        "auto_envoi": db.reglage(R_AUTO_ENVOI, "0") == "1",
        "import": db.reglage(R_IMPORT, "1") == "1",
    }


def statut_vers_clickup(statut: str, mapping: dict | None):
    return mapping.get(statut) if mapping else None


def statut_depuis_clickup(nom: str, mapping: dict | None):
    """Statut ClickUp -> statut local ; None si le mapping est absent ou incomplet."""
    if not mapping:
        return None
    for local, distant in mapping.items():
        if distant and distant.lower() == (nom or "").lower():
            return local
    return None


def priorite_depuis_clickup(p) -> str:
    """Priorité ClickUp (1 à 4, ou aucune) -> priorité locale (aucune = normale)."""
    return PRIO_DEPUIS_CLICKUP.get(p, "normale")


_PREFIXE = re.compile(r"^\s*\[([^\]]+)\]\s*")


def titre_local(nom_clickup: str) -> str:
    """« [Client] Titre » -> « Titre »."""
    return _PREFIXE.sub("", nom_clickup or "").strip()


def titre_clickup(titre: str, client: dict | None) -> str:
    """Titre local -> nom ClickUp, préfixé par le client (sauf client interne)."""
    if client and not client.get("interne"):
        return f"[{client['nom']}] {titre}"
    return titre


def client_depuis_nom(nom_clickup: str, clients: list):
    """Si le nom commence par [Nom de client] et que ce client existe, son id."""
    m = _PREFIXE.match(nom_clickup or "")
    if not m:
        return None
    cible = m.group(1).strip().lower()
    return next((c["id"] for c in clients if (c["nom"] or "").strip().lower() == cible), None)


def valeurs_distantes(r: dict, mapping) -> dict:
    """Tâche ClickUp normalisée -> valeurs comparables aux champs locaux."""
    return {
        "titre": titre_local(r["nom"]),
        "statut": statut_depuis_clickup(r["statut"], mapping),
        "priorite": priorite_depuis_clickup(r["priorite"]),
        "date_limite": r["date_limite"],
    }


def payload_clickup(champs: dict, client: dict | None, mapping) -> dict:
    """Valeurs locales -> corps de requête ClickUp (seulement les champs fournis)."""
    p = {}
    if "titre" in champs:
        p["name"] = titre_clickup(champs["titre"], client)
    if "statut" in champs and statut_vers_clickup(champs["statut"], mapping):
        p["status"] = statut_vers_clickup(champs["statut"], mapping)
    if "priorite" in champs:
        p["priority"] = PRIO_VERS_CLICKUP.get(champs["priorite"], 3)
    if "date_limite" in champs:
        p["due_date"] = cu.date_vers_ms(champs["date_limite"])
        p["due_date_time"] = False
    return p


def _a_envoyer_auto(t: dict, client: dict | None, aujourd_hui: date) -> bool:
    """Option « envoi automatique » : tâches urgentes ou dues dans la semaine."""
    if t["clickup_task_id"] or t["statut"] == "valide":
        return False
    if not client or client["statut_projet"] == "archive":
        return False
    return t["priorite"] == "urgente" or bool(
        t["date_limite"] and t["date_limite"] <= aujourd_hui + timedelta(days=7))


# ---------------------------------------------------------------------------
# 1. Planification (pure)
# ---------------------------------------------------------------------------
def planifier(taches: list, clients: list, distantes: list, regl: dict,
              aujourd_hui: date | None = None) -> list:
    """Compare les deux côtés et renvoie la liste des actions à faire."""
    aujourd_hui = aujourd_hui or date.today()
    mapping = regl["mapping"]
    par_id = {r["id"]: r for r in distantes}
    clients_par_id = {c["id"]: c for c in clients}
    actions = []
    ids_lies = {t["clickup_task_id"] for t in taches if t["clickup_task_id"]}

    for t in taches:
        if not t["clickup_task_id"]:
            if regl["auto_envoi"] and _a_envoyer_auto(t, clients_par_id.get(t["client_id"]), aujourd_hui):
                actions.append({"type": "envoyer", "tache_id": t["id"], "champ": "",
                                "avant": "", "apres": t["titre"]})
            continue

        r = par_id.get(t["clickup_task_id"])
        if r is None:
            # Disparue de la liste ClickUp : on la signale, on n'efface rien
            if not t["clickup_delie"]:
                actions.append({"type": "delier", "tache_id": t["id"], "champ": "",
                                "avant": t["clickup_task_id"], "apres": ""})
            continue
        if t["clickup_delie"]:
            actions.append({"type": "relier", "tache_id": t["id"], "champ": "",
                            "avant": "", "apres": r["id"]})

        dist = valeurs_distantes(r, mapping)
        diffs = []
        for champ in CHAMPS:
            if champ == "statut" and dist["statut"] is None:
                continue  # mapping absent ou statut ClickUp non mappé : on n'y touche pas
            if t[champ] != dist[champ]:
                diffs.append(champ)

        loc_t = t["updated_at"] or t["created_at"] or datetime.min
        rem_t = r["date_updated"] or datetime.min
        base = t["clickup_updated_at"]

        if not diffs:
            if rem_t != base:  # mémorise le dernier état connu, sans rien changer d'autre
                actions.append({"type": "base", "tache_id": t["id"], "champ": "",
                                "avant": base, "apres": rem_t})
            continue

        local_modifie = base is None or loc_t > base
        distant_modifie = base is None or rem_t > base
        conflit = local_modifie and distant_modifie and abs(loc_t - rem_t) < ECART_CONFLIT
        for champ in diffs:
            if conflit:
                typ = "conflit"
            elif loc_t > rem_t:
                typ = "pousser"
            else:
                typ = "tirer"
            actions.append({
                "type": typ, "tache_id": t["id"], "champ": champ,
                "avant": dist[champ] if typ == "pousser" else t[champ],
                "apres": t[champ] if typ == "pousser" else dist[champ],
                "local": t[champ], "distant": dist[champ], "rem_t": rem_t,
            })

    if regl["import"]:
        for r in distantes:
            if r["id"] in ids_lies or r["statut_type"] == "closed":
                continue
            actions.append({"type": "importer", "tache_id": None, "champ": "", "avant": "",
                            "apres": r["nom"], "distante": r,
                            "client_id": client_depuis_nom(r["nom"], clients)})
    return actions


def resume_action(a: dict, taches_par_id: dict) -> str:
    """Phrase lisible pour l'aperçu (mode simulation) et le journal."""
    t = taches_par_id.get(a["tache_id"])
    nom = f"« {t['titre']} »" if t else ""
    champ = LIBELLES_CHAMPS.get(a["champ"], a["champ"])
    return {
        "envoyer": f"Créer dans ClickUp la tâche {nom}",
        "delier": f"Marquer {nom} comme déliée (introuvable dans ClickUp)",
        "relier": f"Relier de nouveau {nom} à ClickUp",
        "pousser": f"{nom} : {champ} « {_fmt(a['avant'])} » → « {_fmt(a['apres'])} » dans ClickUp",
        "tirer": f"{nom} : {champ} « {_fmt(a['avant'])} » → « {_fmt(a['apres'])} » depuis ClickUp",
        "conflit": f"Conflit sur {nom} ({champ}) : local « {_fmt(a.get('local'))} », "
                   f"ClickUp « {_fmt(a.get('distant'))} » — à trancher",
        "importer": f"Importer la tâche ClickUp « {a['apres']} »",
        "base": "",
    }.get(a["type"], a["type"])


def _fmt(v):
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if v in (None, ""):
        return "aucune"
    return {**db.TACHE_STATUTS, **db.PRIORITES}.get(v, v)


# ---------------------------------------------------------------------------
# 2. Application
# ---------------------------------------------------------------------------
def envoyer_tache(t: dict, mapping=None) -> dict:
    """Crée la tâche dans ClickUp (bouton « Envoyer vers ClickUp » ou envoi auto).
    Refuse une tâche déjà liée : jamais de doublon."""
    if t.get("clickup_task_id"):
        raise cu.ClickUpError("Cette tâche est déjà liée à ClickUp.")
    c = db.client(t["client_id"])
    description = t["description"] or ""
    description += f"\n\nClient : {c['nom']}" if c else ""
    if c and c.get("site_url"):
        description += f"\nSite : {c['site_url']}"
    payload = payload_clickup({k: t[k] for k in CHAMPS}, c, mapping)
    payload.update(description=description.strip(), tags=["dashboard"])
    r = cu.creer_tache(cu.list_id(), payload)
    db.update_tache(t["id"], {"clickup_task_id": r["id"], "clickup_url": r["url"],
                              "clickup_updated_at": r["date_updated"], "clickup_delie": False},
                    touch=False)
    db.add_historique(t["client_id"], "tache", f"Tâche « {t['titre']} » envoyée vers ClickUp.")
    db.add_sync_log("vers_clickup", t["id"], "creation", "", payload.get("name"), "envoyé")
    cu.vider_cache()
    return r


def lier(t: dict, r: dict):
    """Rattache une tâche locale existante à une tâche ClickUp choisie."""
    db.update_tache(t["id"], {"clickup_task_id": r["id"], "clickup_url": r["url"],
                              "clickup_updated_at": None, "clickup_delie": False}, touch=False)
    db.add_historique(t["client_id"], "tache", f"Tâche « {t['titre']} » liée à ClickUp.")
    db.add_sync_log("depuis_clickup", t["id"], "liaison", "", r["nom"], "lié")


def appliquer(actions: list, regl: dict) -> dict:
    """Exécute le plan. Renvoie les compteurs {vers_clickup, depuis_clickup, erreurs}."""
    mapping = regl["mapping"]
    stats = {"vers_clickup": 0, "depuis_clickup": 0, "erreurs": 0, "conflits": 0}

    # Regroupe par tâche : un seul PUT ClickUp et une seule écriture locale par tâche
    par_tache = {}
    for a in actions:
        par_tache.setdefault((a["type"], a["tache_id"]), []).append(a)

    for (typ, tid), lot in par_tache.items():
        t = db.tache(tid) if tid is not None else None
        try:
            if typ == "envoyer" and t:
                envoyer_tache(t, mapping)
                stats["vers_clickup"] += 1
            elif typ == "delier" and t:
                db.update_tache(tid, {"clickup_delie": True}, touch=False)
                db.add_sync_log("depuis_clickup", tid, "lien", t["clickup_task_id"], "", "délié")
                db.add_historique(t["client_id"], "tache",
                                  f"Tâche « {t['titre']} » introuvable dans ClickUp : marquée déliée.")
            elif typ == "relier" and t:
                db.update_tache(tid, {"clickup_delie": False}, touch=False)
                db.add_sync_log("depuis_clickup", tid, "lien", "", t["clickup_task_id"], "relié")
            elif typ == "base" and t:
                db.update_tache(tid, {"clickup_updated_at": lot[0]["apres"]}, touch=False)
            elif typ == "pousser" and t:
                c = db.client(t["client_id"])
                r = cu.maj_tache(t["clickup_task_id"],
                                 payload_clickup({a["champ"]: a["apres"] for a in lot}, c, mapping))
                db.update_tache(tid, {"clickup_updated_at": r["date_updated"]}, touch=False)
                for a in lot:
                    db.add_sync_log("vers_clickup", tid, a["champ"], _fmt(a["avant"]), _fmt(a["apres"]), "ok")
                stats["vers_clickup"] += len(lot)
            elif typ == "tirer" and t:
                data = {a["champ"]: a["apres"] for a in lot}
                if data.get("statut") == "valide":
                    data.update(date_validation=date.today(), valide_par=t["valide_par"] or "moi")
                elif "statut" in data:
                    data.update(date_validation=None, valide_par=None)
                rem_t = lot[0]["rem_t"]
                data.update(updated_at=rem_t, clickup_updated_at=rem_t)
                db.update_tache(tid, data, touch=False)
                for a in lot:
                    db.add_sync_log("depuis_clickup", tid, a["champ"], _fmt(a["avant"]), _fmt(a["apres"]), "ok")
                    db.add_historique(t["client_id"], "validation" if a["apres"] == "valide" else "tache",
                                      f"« {t['titre']} » : {LIBELLES_CHAMPS[a['champ']].lower()} passé(e) "
                                      f"à {_fmt(a['apres']).lower()} depuis ClickUp.")
                stats["depuis_clickup"] += len(lot)
            elif typ == "conflit" and t:
                for a in lot:
                    # Un seul conflit ouvert par tâche et par champ (idempotence)
                    deja = any(l["tache_id"] == tid and l["champ"] == a["champ"] and l["resultat"] == "conflit"
                               for l in db.sync_log())
                    if not deja:
                        db.add_sync_log("depuis_clickup", tid, a["champ"], _fmt(a["local"]),
                                        _fmt(a["distant"]), "conflit")
                stats["conflits"] += len(lot)
            elif typ == "importer":
                for a in lot:
                    importer(a["distante"], a["client_id"], mapping)
                    stats["depuis_clickup"] += 1
        except cu.ClickUpError as e:
            stats["erreurs"] += 1
            db.add_sync_log("vers_clickup" if typ in ("envoyer", "pousser") else "depuis_clickup",
                            tid, lot[0]["champ"], "", "", f"erreur : {e}")
    return stats


def importer(r: dict, client_id, mapping):
    """Crée localement une tâche née dans ClickUp, déjà liée."""
    cid = client_id or db.client_interne_id()
    statut = statut_depuis_clickup(r["statut"], mapping) or "a_faire"
    tid = db.create_tache({
        "client_id": cid, "titre": titre_local(r["nom"]), "description": r["description"],
        "statut": statut, "priorite": priorite_depuis_clickup(r["priorite"]),
        "date_limite": r["date_limite"], "clickup_task_id": r["id"], "clickup_url": r["url"],
        "clickup_updated_at": r["date_updated"], "updated_at": r["date_updated"],
        "valide_par": "moi" if statut == "valide" else None,
    })
    db.add_sync_log("depuis_clickup", tid, "creation", "", r["nom"], "importé")
    db.add_historique(cid, "tache", f"Tâche « {titre_local(r['nom'])} » importée depuis ClickUp.")


def resoudre_conflit(log: dict, garder: str, regl: dict):
    """Applique la version choisie (« local » ou « clickup ») d'un conflit."""
    t = db.tache(log["tache_id"])
    if not t:
        db.update_sync_log(log["id"], {"resultat": "conflit ignoré (tâche supprimée)"})
        return
    champ = log["champ"]
    if garder == "local":
        c = db.client(t["client_id"])
        r = cu.maj_tache(t["clickup_task_id"], payload_clickup({champ: t[champ]}, c, regl["mapping"]))
        db.update_tache(t["id"], {"clickup_updated_at": r["date_updated"]}, touch=False)
    else:
        r = next((x for x in cu.taches_liste(cu.list_id()) if x["id"] == t["clickup_task_id"]), None)
        if r:
            val = valeurs_distantes(r, regl["mapping"])[champ]
            db.update_tache(t["id"], {champ: val, "updated_at": r["date_updated"],
                                      "clickup_updated_at": r["date_updated"]}, touch=False)
            db.add_historique(t["client_id"], "tache", f"« {t['titre']} » : conflit résolu avec la version ClickUp.")
    db.update_sync_log(log["id"], {"resultat": f"conflit résolu ({'local' if garder == 'local' else 'ClickUp'})"})
    cu.vider_cache()


def synchroniser(simulation: bool | None = None) -> dict:
    """Lance une synchro complète. En simulation : renvoie le plan sans rien écrire."""
    regl = reglages()
    simulation = regl["simulation"] if simulation is None else simulation
    cu.vider_cache()
    distantes = cu.taches_liste(cu.list_id(), True)
    taches = db.taches()
    plan = planifier(taches, db.clients(), distantes, regl)
    visibles = [a for a in plan if a["type"] != "base"]
    if simulation:
        return {"simulation": True, "plan": visibles, "taches": taches}
    stats = appliquer(plan, regl)
    db.set_reglages({R_DERNIERE: datetime.now().isoformat(timespec="seconds")})
    cu.vider_cache()
    return {"simulation": False, "plan": visibles, "stats": stats, "taches": taches}


def derniere_synchro():
    v = db.reglage(R_DERNIERE)
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def synchro_auto():
    """Au chargement de l'app : synchro réelle si configurée, hors simulation,
    et si la dernière date de plus de 5 minutes. Ne lève jamais d'erreur."""
    if not cu.configure():
        return None
    regl = reglages()
    if regl["simulation"]:
        return None
    derniere = derniere_synchro()
    if derniere and datetime.now() - derniere < INTERVALLE_AUTO:
        return None
    try:
        return synchroniser(simulation=False)
    except cu.ClickUpError as e:
        db.set_reglages({R_DERNIERE: datetime.now().isoformat(timespec="seconds")})
        db.add_sync_log("depuis_clickup", None, "", "", "", f"erreur : {e}")
        return None

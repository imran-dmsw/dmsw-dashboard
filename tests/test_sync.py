"""Tests de l'intégration ClickUp (réponses simulées, aucun appel réel)."""
from datetime import date, datetime, timedelta

import clickup_client as cu
import sync
from conftest import MAPPING, configurer


# --- Correspondances statuts et priorités ------------------------------------------
def test_mapping_statuts():
    assert sync.statut_vers_clickup("en_cours", MAPPING) == "in progress"
    assert sync.statut_depuis_clickup("Complete", MAPPING) == "valide"  # insensible à la casse
    assert sync.statut_depuis_clickup("review", MAPPING) is None        # statut non mappé
    assert sync.statut_depuis_clickup("to do", None) is None            # mapping absent


def test_mapping_priorites():
    for local, distant in {"urgente": 1, "haute": 2, "normale": 3, "basse": 4}.items():
        assert sync.PRIO_VERS_CLICKUP[local] == distant
        assert sync.priorite_depuis_clickup(distant) == local
    assert sync.priorite_depuis_clickup(None) == "normale"


# --- Dates ---------------------------------------------------------------------------
def test_conversion_dates_aller_retour():
    for d in (date(2026, 1, 1), date(2026, 3, 29), date(2026, 10, 25), date(2026, 12, 31)):
        assert cu.date_depuis_ms(cu.date_vers_ms(d)) == d  # y compris jours de changement d'heure


def test_conversion_aucune_date():
    assert cu.date_vers_ms(None) is None
    assert cu.date_depuis_ms(None) is None
    assert cu.date_depuis_ms("") is None


def test_date_clickup_minuit_paris():
    # 23 h 30 UTC le 24/10 = 01 h 30 le 25/10 à Paris : la date doit être le 25
    ms = int(datetime(2026, 10, 24, 23, 30, tzinfo=cu.PARIS).timestamp() * 1000) + 2 * 3600 * 1000
    assert cu.date_depuis_ms(ms) == date(2026, 10, 25)


# --- Règle « le plus récent gagne » ----------------------------------------------------
def _tache(**k):
    t = {"id": 1, "client_id": 1, "titre": "Logo", "statut": "a_faire", "priorite": "normale",
         "date_limite": None, "clickup_task_id": "cu1", "clickup_delie": False,
         "created_at": datetime(2026, 10, 1), "updated_at": datetime(2026, 10, 10, 9, 0),
         "clickup_updated_at": datetime(2026, 10, 9), "valide_par": None}
    t.update(k)
    return t


def _distante(**k):
    r = {"id": "cu1", "nom": "[Client] Logo", "statut": "to do", "statut_type": "open", "priorite": 3,
         "date_limite": None, "date_updated": datetime(2026, 10, 9), "url": "u", "description": ""}
    r.update(k)
    return r


REGL = {"mapping": MAPPING, "simulation": False, "auto_envoi": False, "import": False}
CLIENTS = [{"id": 1, "nom": "Client", "interne": False, "statut_projet": "en_cours"}]


def test_clickup_plus_recent_gagne():
    t = _tache(updated_at=datetime(2026, 10, 10, 9, 0))
    r = _distante(statut="complete", date_updated=datetime(2026, 10, 10, 12, 0))
    plan = sync.planifier([t], CLIENTS, [r], REGL)
    assert [(a["type"], a["champ"], a["apres"]) for a in plan] == [("tirer", "statut", "valide")]


def test_local_plus_recent_gagne():
    t = _tache(priorite="urgente", updated_at=datetime(2026, 10, 10, 15, 0))
    r = _distante(date_updated=datetime(2026, 10, 10, 12, 0))
    plan = sync.planifier([t], CLIENTS, [r], REGL)
    assert [(a["type"], a["champ"], a["apres"]) for a in plan] == [("pousser", "priorite", "urgente")]


def test_conflit_moins_de_2_minutes():
    t = _tache(titre="Logo v2", updated_at=datetime(2026, 10, 10, 12, 0, 30))
    r = _distante(nom="[Client] Logo v3", date_updated=datetime(2026, 10, 10, 12, 1, 0))
    plan = sync.planifier([t], CLIENTS, [r], REGL)
    assert [a["type"] for a in plan] == ["conflit"]


def test_tache_disparue_deliee_sans_suppression():
    plan = sync.planifier([_tache()], CLIENTS, [], REGL)
    assert [a["type"] for a in plan] == ["delier"]


def test_titre_garde_le_prefixe_client():
    assert sync.titre_clickup("Logo", CLIENTS[0]) == "[Client] Logo"
    assert sync.titre_local("[Client] Logo") == "Logo"
    assert sync.titre_clickup("Bot", {"nom": "DMSW (interne)", "interne": True}) == "Bot"


# --- Envoi, double synchro, client interne (base SQLite jetable) -----------------------
def test_envoi_sans_doublon(base, clickup):
    configurer()
    cid = base.create_client({"nom": "Boulangerie Paul", "site_url": "https://paul.fr"})
    tid = base.create_tache({"client_id": cid, "titre": "Mentions légales", "priorite": "haute",
                             "date_limite": date(2026, 11, 5)})
    r = sync.envoyer_tache(base.tache(tid), MAPPING)
    assert r["nom"] == "[Boulangerie Paul] Mentions légales"
    assert r["priorite"] == 2 and r["date_limite"] == date(2026, 11, 5) and "dashboard" in r["tags"]
    assert base.tache(tid)["clickup_task_id"] == r["id"]
    try:
        sync.envoyer_tache(base.tache(tid), MAPPING)
        assert False, "un 2e envoi aurait dû être refusé"
    except cu.ClickUpError:
        pass
    assert clickup.appels["creer"] == 1


def test_double_synchro_idempotente(base, clickup):
    configurer(auto_envoi=True, importer=True)
    cid = base.create_client({"nom": "Garage Martin", "statut_projet": "en_cours"})
    base.create_tache({"client_id": cid, "titre": "Sauvegarde", "priorite": "urgente"})
    clickup.ajouter("Réparer le bot de prospection")
    clickup.ajouter("[Garage Martin] Changer les photos", statut="in progress", priorite=2)

    premier = sync.synchroniser(simulation=False)
    assert premier["stats"]["erreurs"] == 0
    nb_local, nb_distant = len(base.taches()), len(clickup.taches)
    assert (nb_local, nb_distant) == (3, 3)
    appels = dict(clickup.appels)
    logs = len(base.sync_log())

    second = sync.synchroniser(simulation=False)
    assert second["plan"] == []                                   # rien à faire
    assert (len(base.taches()), len(clickup.taches)) == (nb_local, nb_distant)
    assert clickup.appels == appels                               # aucun appel d'écriture
    assert len(base.sync_log()) == logs                           # aucun changement en trop


def test_rattachement_client_interne_et_prefixe(base, clickup):
    configurer(importer=True)
    cid = base.create_client({"nom": "Garage Martin"})
    clickup.ajouter("Réparer le bot de prospection")
    clickup.ajouter("[garage martin] Changer les photos")
    clickup.ajouter("Tâche fermée", ferme=True)
    sync.synchroniser(simulation=False)

    interne = [c for c in base.clients() if c["interne"]]
    assert len(interne) == 1 and interne[0]["nom"] == "DMSW (interne)"
    titres = {t["titre"]: t["client_id"] for t in base.taches()}
    assert titres == {"Réparer le bot de prospection": interne[0]["id"], "Changer les photos": cid}


def test_statut_change_dans_clickup_puis_synchro(base, clickup):
    configurer(importer=False)
    cid = base.create_client({"nom": "Atelier Nova"})
    tid = base.create_tache({"client_id": cid, "titre": "HTTPS"})
    sync.envoyer_tache(base.tache(tid), MAPPING)
    remote_id = base.tache(tid)["clickup_task_id"]

    clickup.decalage = timedelta(minutes=10)                      # modifié dans ClickUp plus tard
    clickup.maj_tache(remote_id, {"status": "complete"})
    sync.synchroniser(simulation=False)
    t = base.tache(tid)
    assert t["statut"] == "valide" and t["date_validation"] is not None
    assert any("depuis ClickUp" in h["texte"] for h in base.historique(cid))


def test_simulation_n_ecrit_rien(base, clickup):
    configurer(simulation=True, importer=True)
    clickup.ajouter("Réparer le bot de prospection")
    res = sync.synchroniser()
    assert res["simulation"] and [a["type"] for a in res["plan"]] == ["importer"]
    assert base.taches() == [] and base.sync_log() == []

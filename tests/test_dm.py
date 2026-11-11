"""Suivi des DM : import Instagram simulé (aucun appel réel), relances, conversion en client."""
from datetime import date, datetime, timedelta

import pytest

import db
import dm
import instagram_client as ig


class FauxInstagram:
    """Imite l'API : conversations + dernier message de chacune."""

    def __init__(self):
        self.convs = {}
        self.appels_detail = 0

    def ajouter(self, cid, autre, texte, de_moi=False, il_y_a=timedelta(hours=1)):
        quand = datetime.now() - il_y_a
        self.convs[cid] = {
            "updated_time": quand,
            "message": {"de_id": "moi-id" if de_moi else f"id-{autre}",
                        "de_username": "dmsw.agence" if de_moi else autre,
                        "a_id": f"id-{autre}" if de_moi else "moi-id",
                        "a_username": autre if de_moi else "dmsw.agence", "texte": texte, "date": quand}}

    def conversations(self, maximum=100):
        tri = sorted(self.convs.items(), key=lambda kv: kv[1]["updated_time"], reverse=True)
        return [{"id": k, "updated_time": v["updated_time"]} for k, v in tri][:maximum]

    def dernier_message(self, cid):
        self.appels_detail += 1
        return dict(self.convs[cid]["message"])

    def moi(self):
        return {"id": "moi-id", "username": "dmsw.agence"}


@pytest.fixture
def insta(monkeypatch):
    faux = FauxInstagram()
    monkeypatch.setattr(ig, "conversations", faux.conversations)
    monkeypatch.setattr(ig, "dernier_message", faux.dernier_message)
    monkeypatch.setattr(ig, "moi", faux.moi)
    return faux


def test_import_cree_puis_ne_duplique_pas(base, insta):
    insta.ajouter("c1", "boulangerie.paul", "Bonjour, combien pour un site ?")
    insta.ajouter("c2", "coiffure.lea", "Je vous recontacte", de_moi=True)
    s1 = dm.importer_instagram()
    assert s1["crees"] == 2
    p = {x["pseudo"]: x for x in db.prospects()}
    assert p["boulangerie.paul"]["dernier_message_de"] == "eux" and dm.a_repondre(p["boulangerie.paul"])
    assert p["coiffure.lea"]["dernier_message_de"] == "moi" and not dm.a_repondre(p["coiffure.lea"])
    assert p["boulangerie.paul"]["profil_url"] == "https://www.instagram.com/boulangerie.paul/"

    appels = insta.appels_detail
    s2 = dm.importer_instagram()
    assert s2["crees"] == 0 and s2["inchanges"] == 2 and len(db.prospects()) == 2
    assert insta.appels_detail == appels  # rien de nouveau : aucun appel de détail


def test_nouveau_message_met_a_jour_sans_toucher_au_statut(base, insta):
    insta.ajouter("c1", "garage.martin", "Merci, je réfléchis", il_y_a=timedelta(days=2))
    dm.importer_instagram()
    p = db.prospects()[0]
    db.update_prospect(p["id"], {"statut": "devis"})
    insta.ajouter("c1", "garage.martin", "C'est ok pour le devis !", il_y_a=timedelta(minutes=5))
    s = dm.importer_instagram()
    p = db.prospects()[0]
    assert s["mis_a_jour"] == 1 and p["statut"] == "devis" and "ok pour le devis" in p["apercu"]


def test_apercu_tronque(base, insta):
    insta.ajouter("c1", "long", "x" * 500)
    dm.importer_instagram()
    assert len(db.prospects()[0]["apercu"]) == dm.APERCU_MAX


def test_conversation_supprimee_jamais_reimportee(base, insta):
    insta.ajouter("c1", "spam.compte", "Promo !!!")
    dm.importer_instagram()
    dm.supprimer(db.prospects()[0])
    insta.ajouter("c1", "spam.compte", "Encore une promo", il_y_a=timedelta(minutes=1))
    dm.importer_instagram()
    assert db.prospects() == []


def test_relance_et_conversion_en_client(base):
    pid = db.create_prospect({"plateforme": "tiktok", "pseudo": "kimono.shop", "nom": "Kimono",
                              "secteur": "Boutique", "dernier_message_de": "eux"})
    p = db.prospect(pid)
    dm.marquer_relance(p)
    p = db.prospect(pid)
    assert p["statut"] == "relance" and p["prochaine_relance"] == date.today() + timedelta(days=3)
    assert not dm.relance_due(p) and dm.relance_due(p, date.today() + timedelta(days=3))

    cid = dm.convertir_en_client(p)
    c = db.client(cid)
    assert c["nom"] == "Kimono" and c["statut_projet"] == "prospect" and "TikTok (@kimono.shop)" in c["notes"]
    assert db.prospect(pid)["statut"] == "converti" and db.prospect(pid)["client_lie_id"] == cid
    assert dm.convertir_en_client(db.prospect(pid)) == cid  # pas de deuxième fiche
    assert len(db.clients()) == 1


def test_url_profils():
    assert dm.profil_url("tiktok", "@kimono.shop") == "https://www.tiktok.com/@kimono.shop"
    assert dm.profil_url("autre", "x") == ""


class Reponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def test_jeton_expire_message_clair_sans_jeton(monkeypatch):
    monkeypatch.setattr(ig, "_token", lambda: "IGAA-jeton-secret")
    monkeypatch.setattr(ig, "PAUSE", 0)
    monkeypatch.setattr(ig.requests, "get", lambda *a, **k: Reponse(400, {"error": {"code": 190, "message": "expired"}}))
    with pytest.raises(ig.InstagramError) as e:
        ig.conversations()
    assert "expiré" in str(e.value) and "IGAA" not in str(e.value)

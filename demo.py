"""Données de démonstration : 4 faux clients, dates calculées à partir d'aujourd'hui.

Les clients de démo ont un nom qui commence par « [Démo] ». Le chargement
n'ajoute que des lignes : il ne modifie ni ne supprime jamais de vraies données.
"""
from datetime import date, timedelta

import db


def _j(n):
    """Aujourd'hui + n jours (n négatif = dans le passé)."""
    return date.today() + timedelta(days=n)


CLIENTS = [
    {   # Restaurant livré : solde impayé (rouge), domaine qui expire (rouge), SEO à faire
        "nom": "Le Petit Bistrot", "activite": "Restaurant", "site_url": "lepetitbistrot-demo.fr",
        "domaine": "lepetitbistrot-demo.fr", "contact_nom": "Sophie Martin", "contact_tel": "06 00 00 00 01",
        "contact_email": "contact@lepetitbistrot-demo.fr", "date_livraison": _j(-40), "statut_projet": "livre",
        "prix_site": 1200, "acompte_recu": 600, "solde_restant": 600, "abonnement_mensuel": 0,
        "paiement_a_jour": False, "hebergeur": "IONOS", "stack": "Lovable",
        "date_renouvellement_domaine": _j(5), "date_renouvellement_hebergement": _j(120),
        "emplacement_acces": "Gestionnaire de mots de passe, dossier Clients/Bistrot",
        "seo_statut": "a_faire", "fiche_google_statut": "en_cours", "https_actif": True,
        "double_auth": True, "corrections_incluses": 2, "corrections_utilisees": 1,
        "notes": "Menu du soir à mettre en ligne chaque saison.",
    },
    {   # Avocat en cours de création : rien d'urgent, tâches à venir
        "nom": "Maître Durand – Avocat", "activite": "Cabinet d'avocat", "site_url": "",
        "domaine": "durand-avocat-demo.fr", "contact_nom": "Paul Durand", "contact_tel": "06 00 00 00 02",
        "contact_email": "cabinet@durand-avocat-demo.fr", "statut_projet": "en_cours",
        "prix_site": 1500, "acompte_recu": 750, "solde_restant": 750, "stack": "Lovable",
        "hebergeur": "Lovable", "emplacement_acces": "Gestionnaire de mots de passe, dossier Clients/Durand",
        "double_auth": True, "corrections_incluses": 3, "corrections_utilisees": 0,
    },
    {   # Boutique Shopify : HTTPS inactif (rouge), 2FA absente, corrections épuisées, hébergement bientôt
        "nom": "Atelier Nova", "activite": "Boutique de vêtements (Shopify)", "site_url": "ateliernova-demo.com",
        "domaine": "ateliernova-demo.com", "contact_nom": "Inès Benali", "contact_tel": "06 00 00 00 03",
        "contact_email": "hello@ateliernova-demo.com", "date_livraison": _j(-20), "statut_projet": "livre",
        "prix_site": 2400, "acompte_recu": 2400, "solde_restant": 0, "stack": "Shopify", "hebergeur": "Shopify",
        "date_renouvellement_domaine": _j(200), "date_renouvellement_hebergement": _j(20),
        "emplacement_acces": "Compte collaborateur Shopify", "seo_statut": "en_cours",
        "fiche_google_statut": "aucune", "search_console": True, "date_dernier_audit_seo": _j(-30),
        "https_actif": False, "double_auth": False, "corrections_incluses": 3, "corrections_utilisees": 3,
    },
    {   # Maintenance : paiement en retard (rouge), sauvegarde ancienne, audit SEO vieux
        "nom": "Garage Martin", "activite": "Garage automobile", "site_url": "garagemartin-demo.fr",
        "domaine": "garagemartin-demo.fr", "contact_nom": "Luc Martin", "contact_tel": "06 00 00 00 04",
        "contact_email": "garage@garagemartin-demo.fr", "date_livraison": _j(-300), "statut_projet": "maintenance",
        "prix_site": 900, "acompte_recu": 900, "solde_restant": 0, "abonnement_mensuel": 29.99,
        "date_prochain_paiement": _j(-3), "paiement_a_jour": True, "hebergeur": "IONOS", "stack": "Lovable",
        "date_renouvellement_domaine": _j(60), "date_renouvellement_hebergement": _j(60),
        "emplacement_acces": "Gestionnaire de mots de passe, dossier Clients/Garage",
        "seo_statut": "bon", "fiche_google_statut": "optimisee", "search_console": True,
        "date_dernier_audit_seo": _j(-120), "https_actif": True, "double_auth": True,
        "date_derniere_sauvegarde": _j(-75), "date_derniere_mise_a_jour": _j(-10),
        "corrections_incluses": 2, "corrections_utilisees": 0,
    },
]

# (index client, titre, statut, priorité, date limite en jours)
TACHES = [
    (0, "Ajouter le menu du soir", "en_cours", "haute", -2),
    (0, "Créer la fiche Google Business", "a_faire", "normale", 3),
    (0, "Relancer pour le solde", "a_faire", "urgente", 0),
    (0, "Mise en ligne et HTTPS", "valide", "normale", -40),
    (1, "Devis signé et acompte reçu", "valide", "normale", -10),
    (1, "Maquette ou site démo validé", "en_cours", "haute", 2),
    (1, "Mentions légales et RGPD", "a_faire", "normale", 10),
    (1, "Formulaire de contact testé", "a_faire", "basse", 20),
    (2, "Activer HTTPS sur le domaine", "a_faire", "urgente", 1),
    (2, "Proposer la maintenance à 29,99 €/mois", "a_faire", "normale", 14),
    (3, "Sauvegarde mensuelle", "a_faire", "haute", -5),
    (3, "Rapport mensuel de maintenance", "a_faire", "normale", 6),
]


def demo_presente() -> bool:
    return any((c["nom"] or "").startswith(db.DEMO_PREFIX) for c in db.clients())


def charger() -> int:
    """Ajoute les clients de démo. Retourne le nombre de clients créés (0 si déjà là)."""
    if demo_presente():
        return 0
    ids = []
    for c in CLIENTS:
        ids.append(db.create_client({**c, "nom": db.DEMO_PREFIX + c["nom"]}))
    for i, titre, statut, prio, delai in TACHES:
        data = {"client_id": ids[i], "titre": titre, "statut": statut, "priorite": prio,
                "date_limite": _j(delai)}
        if statut == "valide":
            data.update(valide_par="moi", date_validation=_j(delai))
        db.create_tache(data)
    db.add_historique(ids[0], "paiement", "Acompte reçu (600,00 €).")
    db.add_historique(ids[3], "technique", "Mise à jour des extensions effectuée.")
    db.add_historique(ids[3], "paiement", "Paiement d'abonnement reçu (29,99 €).")
    return len(ids)


def supprimer() -> int:
    """Supprime uniquement les clients dont le nom commence par « [Démo] »."""
    n = 0
    for c in db.clients():
        if (c["nom"] or "").startswith(db.DEMO_PREFIX):
            db.delete_client(c["id"])
            n += 1
    return n

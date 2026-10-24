# DMSW. — Tableau de bord interne

Suivi des clients de l'agence DMSW (Développe Mon Site Web) : tâches du jour, projets,
paiements, renouvellements, SEO et sécurité. Application Streamlit, en français.

## Lancer en local (aucune configuration)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Sans secrets, l'app utilise SQLite (`data/dmsw.db`) et le mot de passe est **`dmsw`**.
Pour choisir le tien en local : `APP_PASSWORD=monmotdepasse streamlit run app.py`.
Ensuite : ⚙️ Paramètres → « Charger des données de démo » pour voir l'app remplie.

## Brancher Supabase et déployer sur Streamlit Cloud (10 lignes)

1. Ouvre ton projet Supabase (un projet déjà utilisé ailleurs convient).
2. SQL Editor → New query → colle `schema.sql` → Run (crée uniquement les tables `dmsw_…`).
3. Project Settings → API : copie l'URL du projet et la clé **service_role**.
4. Pousse ce dossier sur un dépôt GitHub **privé** (`secrets.toml` et `data/` sont ignorés).
5. share.streamlit.io → New app → choisis le dépôt, fichier principal `app.py`.
6. Advanced settings → Python 3.11 ou plus.
7. Secrets : colle le contenu de `.streamlit/secrets.toml.example` avec tes vraies valeurs.
8. Choisis un `APP_PASSWORD` long : sans lui, l'app reste bloquée en mode Supabase.
9. Deploy. La barre latérale doit afficher « ☁️ Supabase ».
10. Sauvegarde régulière : ⚙️ Paramètres → « Tout exporter (zip) ».

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | Point d'entrée : thème, mot de passe, navigation |
| `db.py` | Accès aux données, même interface pour Supabase et SQLite |
| `alerts.py` | Règles d'alertes (calculées à chaque chargement, jamais stockées) |
| `ui.py` | Charte DMSW, CSS, voyants, cartes |
| `demo.py` | Données de démonstration |
| `views/` | Une page par fichier |
| `schema.sql` | Tables Supabase |

## Choix pris quand la consigne était ambiguë

- **Mot de passe local** : sans `APP_PASSWORD`, le mot de passe par défaut `dmsw` ne marche
  que si l'app est ouverte sur `localhost`. En ligne, `APP_PASSWORD` est obligatoire, sinon
  l'accès est bloqué.
- **Clé Supabase** : la RLS est activée sans politique, donc seule la clé `service_role`
  peut lire et écrire. Elle reste dans les secrets Streamlit, jamais dans le code.
- **Projet Supabase partagé** : toutes les tables sont préfixées `dmsw_` pour ne jamais
  entrer en collision avec celles d'un autre projet. Attention : la clé `service_role` donne
  aussi accès aux tables de l'autre projet, d'où l'importance de la garder secrète.
- **Seuils d'alertes** : stockés dans une petite table `parametres` (clé / valeur).
- **« Site en ligne » / « site livré »** = statut `livre` ou `maintenance`. Les alertes SEO
  et HTTPS ne concernent que ces sites. La double authentification est vérifiée pour les
  statuts en cours, livré et maintenance. Les clients archivés n'ont aucune alerte.
- **Renouvellement déjà dépassé** = rouge.
- **Corrections** : l'alerte ne s'affiche que si au moins une correction est incluse ou utilisée.
- **« Marquer le paiement reçu »** : avec abonnement, la date avance d'un mois. Sans
  abonnement, le solde restant passe à 0 (ajouté à l'acompte). Dans les deux cas, paiement à
  jour et ligne dans l'historique.
- **Solde restant** : calculé (prix − acompte) par défaut. Décoche la case pour le saisir à la main.
- **Changement de statut d'une tâche** : écrit dans l'historique (type « tâche », ou
  « validation » quand elle passe en validé, avec la date et qui a validé).
- **Checklist de démarrage** : dates limites indicatives de J+0 à J+30.
- **Calendrier** : les paiements d'abonnement sont projetés mois par mois sur 90 jours ;
  les retards sont dans la page Aujourd'hui, pas dans le calendrier.
- **Démo** : les clients de démo sont préfixés « [Démo] ». Le bouton ne fait qu'ajouter, et
  refuse s'ils sont déjà là. Un bouton supprime uniquement ces clients-là.
- **Import CSV** : chaque ligne crée un nouveau client (pas de mise à jour d'un client existant).
- **Historique** : la colonne `date` contient aussi l'heure, pour garder l'ordre dans une même journée.

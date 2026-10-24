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

## Importer tes clients (CSV ou zip)

⚙️ Paramètres → « Import » : dépose `clients.csv`, `taches.csv` et `historique.csv`, ou un
`.zip` qui les contient. Un aperçu indique ce qui sera créé avant de cliquer sur « Importer ».
Rejouer l'import ne crée aucun doublon.

## Intégration ClickUp (optionnelle)

Sans token, l'app fonctionne normalement et les pages ClickUp affichent « Intégration non configurée ».

1. **Token** : ClickUp → ton avatar → Settings → Apps → « API Token » → Generate. Il commence par `pk_`.
2. **Secrets Streamlit** (App → Settings → Secrets), en plus des trois existants :
   `CLICKUP_TOKEN = "pk_..."` et `CLICKUP_LIST_ID = "1200940000007891"`.
3. **Supabase** : relance `schema.sql` dans le SQL Editor (la fin du fichier ajoute les colonnes
   ClickUp sans perte de données ; le script peut être rejoué sans risque).
4. ⚙️ Paramètres → ClickUp : choisis la correspondance des statuts (à faire / en cours / validé).
5. 🔗 Synchronisation : la première synchro est **simulée** (rien n'est écrit). Vérifie l'aperçu,
   puis clique sur « Passer en mode réel ».

Pages : 🗂️ Sprint ClickUp (lecture), bouton « ➡️ Envoyer vers ClickUp » dans l'onglet Tâches
d'une fiche client, 🔗 Synchronisation (journal, conflits, liaison manuelle).

Lancer les tests : `pip install -r requirements-dev.txt` puis `pytest -q`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | Point d'entrée : thème, mot de passe, navigation |
| `db.py` | Accès aux données, même interface pour Supabase et SQLite |
| `alerts.py` | Règles d'alertes (calculées à chaque chargement, jamais stockées) |
| `ui.py` | Charte DMSW, CSS, voyants, cartes |
| `demo.py` | Données de démonstration |
| `import_csv.py` | Import clients / tâches / historique (CSV ou zip) |
| `clickup_client.py` | Appels à l'API ClickUp (lecture, création, mise à jour, erreurs) |
| `sync.py` | Synchronisation ClickUp dans les deux sens |
| `tests/` | Tests `pytest` (ClickUp simulé, aucun appel réel) |
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
  ne concernent que ces sites. Les clients archivés n'ont aucune alerte.
- **Partie Sécurité retirée** (HTTPS, sauvegardes, mises à jour, double authentification) :
  plus d'onglet, de colonne ni d'alerte. Les colonnes restent en base, sans perte de données.
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
- **Design** : le prompt ClickUp reprenait l'ancienne charte sombre (Syne). La charte claire
  validée ensuite est conservée partout.
- **Tableau de bord** (📈) : chiffres de l'agence. « Chiffre d'affaires signé » = prix des sites
  des clients en cours, livrés ou en maintenance. Le client interne et les archivés sont exclus.
- **ClickUp, synchro** : par interrogation (Streamlit ne reçoit pas de webhooks), au chargement
  si la dernière synchro date de plus de 5 minutes (jamais en mode simulation), ou via le bouton.
  « Le plus récent gagne » compare l'heure de dernière modification de la tâche entière
  (`updated_at` local et `date_updated` ClickUp), puis applique champ par champ.
- **Conflit** : les deux côtés ont changé depuis la dernière synchro, à moins de 2 minutes
  d'écart. Rien n'est appliqué tant que tu n'as pas choisi la version dans 🔗 Synchronisation.
- **Statut ClickUp non mappé** (ex. « review ») : le statut de la tâche n'est pas synchronisé,
  les autres champs le sont.
- **Tâche déliée** : colonne `clickup_delie`. Supprimer une tâche dans le dashboard ne supprime
  jamais la tâche ClickUp, et inversement.
- **Import ClickUp** : seules les tâches non fermées sont importées. Le client « DMSW (interne) »
  n'a aucune alerte et n'entre dans aucun total.
- **Aujourd'hui** : la section Sprint ClickUp n'affiche pas les tâches déjà liées au dashboard
  (elles sont déjà dans la liste au-dessus).
- **Dates ClickUp** : une date sans heure est envoyée à midi, heure de Paris, pour éviter tout
  décalage de jour.
- **sync_log.tache_id** : sans clé étrangère, pour garder le journal même si la tâche est supprimée.
- **Protection des données en ligne** : si Supabase n'est pas branché, l'app en ligne refuse de
  démarrer (la base de secours SQLite serait effacée à chaque redémarrage de Streamlit Cloud).
  SQLite reste utilisable en local, sur `localhost`.

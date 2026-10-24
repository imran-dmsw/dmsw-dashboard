-- Tables Supabase du tableau de bord DMSW.
-- À coller dans Supabase > SQL Editor > New query, puis « Run ».
-- Toutes les tables sont préfixées « dmsw_ » : ce script peut tourner dans un projet
-- Supabase déjà utilisé par un autre projet, il ne touche à aucune autre table.

create table if not exists dmsw_clients (
  id bigint generated always as identity primary key,
  -- Identité
  nom text not null,
  activite text,
  site_url text,
  domaine text,
  contact_nom text,
  contact_tel text,
  contact_email text,
  date_livraison date,
  statut_projet text not null default 'prospect'
    check (statut_projet in ('prospect','en_cours','livre','maintenance','archive')),
  notes text,
  -- Argent
  prix_site numeric(10,2) default 0,
  acompte_recu numeric(10,2) default 0,
  solde_restant numeric(10,2) default 0,
  abonnement_mensuel numeric(10,2) default 0,
  date_prochain_paiement date,
  paiement_a_jour boolean default true,
  -- Technique
  hebergeur text,
  date_renouvellement_domaine date,
  date_renouvellement_hebergement date,
  stack text,
  emplacement_acces text,           -- OÙ sont rangés les accès, jamais les mots de passe
  -- SEO
  seo_statut text default 'a_faire' check (seo_statut in ('a_faire','en_cours','bon')),
  fiche_google_statut text default 'aucune'
    check (fiche_google_statut in ('aucune','a_creer','en_cours','optimisee')),
  search_console boolean default false,
  date_dernier_audit_seo date,
  seo_notes text,
  -- Sécurité
  https_actif boolean default false,
  date_derniere_sauvegarde date,
  date_derniere_mise_a_jour date,
  double_auth boolean default false,
  securite_notes text,
  -- Suivi
  corrections_incluses integer default 2,
  corrections_utilisees integer default 0,
  created_at timestamptz default now()
);

create table if not exists dmsw_taches (
  id bigint generated always as identity primary key,
  client_id bigint not null references dmsw_clients(id) on delete cascade,
  titre text not null,
  description text,
  statut text not null default 'a_faire' check (statut in ('a_faire','en_cours','valide')),
  priorite text not null default 'normale' check (priorite in ('basse','normale','haute','urgente')),
  date_limite date,
  valide_par text check (valide_par in ('moi','client')),
  date_validation date,
  created_at timestamptz default now()
);

create table if not exists dmsw_historique (
  id bigint generated always as identity primary key,
  client_id bigint not null references dmsw_clients(id) on delete cascade,
  date timestamptz not null default now(),
  type text not null check (type in ('note','tache','paiement','validation','technique','seo')),
  texte text not null
);

-- Seuils d'alertes modifiables depuis la page Paramètres
create table if not exists dmsw_parametres (
  id bigint generated always as identity primary key,
  cle text unique not null,
  valeur text
);

create index if not exists dmsw_taches_client_idx on dmsw_taches(client_id);
create index if not exists dmsw_historique_client_idx on dmsw_historique(client_id);

-- Sécurité : RLS activé SANS politique => la clé publique « anon » ne voit rien.
-- L'app utilise la clé « service_role » (rangée dans les secrets Streamlit, jamais dans le code).
alter table dmsw_clients enable row level security;
alter table dmsw_taches enable row level security;
alter table dmsw_historique enable row level security;
alter table dmsw_parametres enable row level security;

-- ===========================================================================
-- Migration « intégration ClickUp » (sans perte de données).
-- Peut être rejouée sans risque : chaque ligne vérifie si l'élément existe déjà.
-- ===========================================================================
alter table dmsw_clients add column if not exists interne boolean default false;

alter table dmsw_taches add column if not exists clickup_task_id text;
alter table dmsw_taches add column if not exists clickup_url text;
alter table dmsw_taches add column if not exists clickup_updated_at timestamptz;
alter table dmsw_taches add column if not exists clickup_delie boolean default false;
alter table dmsw_taches add column if not exists updated_at timestamptz default now();
-- Une tâche ClickUp n'est liée qu'à une seule tâche locale (plusieurs NULL autorisés)
create unique index if not exists dmsw_taches_clickup_idx on dmsw_taches(clickup_task_id);

create table if not exists dmsw_sync_log (
  id bigint generated always as identity primary key,
  date timestamptz not null default now(),
  direction text not null check (direction in ('vers_clickup','depuis_clickup')),
  tache_id bigint,                 -- pas de clé étrangère : le journal survit à la tâche
  champ text,
  ancienne_valeur text,
  nouvelle_valeur text,
  resultat text
);
alter table dmsw_sync_log enable row level security;

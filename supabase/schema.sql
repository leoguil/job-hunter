-- ============================================================
-- Job Hunter — Schéma Supabase
-- À coller dans : Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- ── 1. Table jobs (partagée entre tous les utilisateurs) ──────

create table if not exists jobs (
    id          bigserial primary key,
    titre       text not null,
    entreprise  text not null,
    localisation text,
    salaire     text,
    date_publication timestamptz not null,
    description text,
    url         text unique not null,
    source      text not null,
    hash_unique text unique not null,
    date_scraping timestamptz default now()
);

-- Index pour les recherches texte
create index if not exists idx_jobs_date on jobs (date_publication desc);
create index if not exists idx_jobs_source on jobs (source);

-- ── 2. Statuts par utilisateur ────────────────────────────────

create table if not exists job_status (
    id          bigserial primary key,
    user_id     uuid not null references auth.users(id) on delete cascade,
    job_id      bigint not null references jobs(id) on delete cascade,
    statut      text not null default 'a_traiter'
                check (statut in ('a_traiter', 'postule', 'ignore')),
    date_action timestamptz default now(),
    notes       text,
    unique (user_id, job_id)
);

create index if not exists idx_job_status_user on job_status (user_id);

-- ── 3. Paramètres par utilisateur ────────────────────────────

create table if not exists user_settings (
    user_id         uuid primary key references auth.users(id) on delete cascade,
    mots_cles       jsonb not null default '["business developer", "sales ops", "revops"]',
    localisation    jsonb not null default '["Lyon"]',
    salaire_min     integer,
    date_max        integer not null default 30,
    mots_cles_exclus jsonb not null default '[]'
);

-- ── 4. Historique des recherches ─────────────────────────────

create table if not exists search_runs (
    id               bigserial primary key,
    user_id          uuid not null references auth.users(id) on delete cascade,
    date_run         timestamptz default now(),
    nombre_resultats integer default 0,
    nouveaux         integer default 0,
    mots_cles        jsonb
);

create index if not exists idx_search_runs_user on search_runs (user_id, date_run desc);

-- ── 5. Row Level Security ────────────────────────────────────
-- (sécurité Supabase — le backend utilise la clé service qui bypass RLS)

alter table job_status   enable row level security;
alter table user_settings enable row level security;
alter table search_runs  enable row level security;
alter table jobs         enable row level security;

-- Jobs : lisibles par tous les utilisateurs connectés
create policy "jobs_select" on jobs
    for select using (auth.role() = 'authenticated');

create policy "jobs_insert" on jobs
    for insert with check (auth.role() = 'authenticated');

-- Statuts : chaque user voit uniquement les siens
create policy "job_status_all" on job_status
    for all using (auth.uid() = user_id);

-- Settings : chaque user voit uniquement les siens
create policy "user_settings_all" on user_settings
    for all using (auth.uid() = user_id);

-- Historique : chaque user voit uniquement le sien
create policy "search_runs_all" on search_runs
    for all using (auth.uid() = user_id);

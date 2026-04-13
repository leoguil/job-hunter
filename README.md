# Job Hunter

Outil de veille d'offres d'emploi multi-utilisateur.
Scrape Welcome to the Jungle (Algolia) et Hellowork (HTML), déduplique, et permet de suivre ses candidatures.

**Stack :** FastAPI · Supabase (PostgreSQL + Auth) · Render · Vercel

---

## Développement local

### 1. Créer le fichier `.env`

```bash
cp .env.example .env
```

Remplir `.env` avec vos valeurs Supabase :

```env
DATABASE_URL=postgresql://postgres:MOTDEPASSE@db.VOTRE_REF.supabase.co:5432/postgres
SUPABASE_URL=https://VOTRE_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=VOTRE_PUBLISHABLE_KEY
```

### 2. Lancer

```bash
./run.sh
# → http://localhost:8000
```

> Sans `DATABASE_URL`, l'app utilise SQLite automatiquement (scrapers fonctionnels, auth désactivée).

---

## Déploiement production

### Étape 1 — Supabase : créer les tables

1. Aller sur [supabase.com](https://supabase.com) → votre projet → **SQL Editor**
2. Coller et exécuter le contenu de **`supabase/schema.sql`**
3. *(Optionnel)* Désactiver la confirmation email : **Authentication → Settings → Email → Confirm email** → OFF

---

### Étape 2 — Render : déployer le backend

1. Aller sur [render.com](https://render.com) → **New → Web Service**
2. Connecter votre repo GitHub (pousser ce projet d'abord)
3. Render détecte `render.yaml` automatiquement
4. Dans **Environment → Environment Variables**, ajouter :

| Clé | Valeur |
|-----|--------|
| `DATABASE_URL` | Connection string Supabase (voir ci-dessous) |
| `SUPABASE_URL` | `https://VOTRE_REF.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Votre publishable key |

5. Cliquer **Deploy** → noter l'URL (ex: `https://job-hunter-api.onrender.com`)

**Où trouver la DATABASE_URL Supabase :**
Supabase Dashboard → **Project Settings → Database → Connection string → Session mode (port 5432)**

> Le plan gratuit Render s'endort après 15 min d'inactivité. Le premier appel après une longue pause prend ~30 secondes.

---

### Étape 3 — Frontend : configurer et déployer

#### Configurer

Ouvrir `frontend/index.html` et remplir le bloc `CONFIG` :

```js
const CONFIG = {
  SUPABASE_URL:            'https://VOTRE_REF.supabase.co',
  SUPABASE_PUBLISHABLE_KEY: 'VOTRE_PUBLISHABLE_KEY',
  API_URL:                 'https://job-hunter-api.onrender.com',
};
```

#### Déployer sur Vercel

```bash
# Option A — CLI
npm i -g vercel
cd frontend
vercel --prod

# Option B — Dashboard Vercel
# New Project → importer le repo → Root Directory = "frontend" → Deploy
```

---

## Structure du projet

```
job-hunter/
├── backend/
│   ├── main.py           # FastAPI — routes API (toutes protégées par auth)
│   ├── auth.py           # Validation token via API Supabase (sans JWT secret)
│   ├── database.py       # SQLAlchemy → PostgreSQL (SQLite en dev si pas de .env)
│   ├── models.py         # jobs, job_status, user_settings, search_runs
│   ├── schemas.py        # Schémas Pydantic
│   └── scrapers/
│       ├── base.py       # Utilitaires communs (hash, HTTP, dates)
│       ├── wttj.py       # Welcome to the Jungle — API Algolia
│       └── hellowork.py  # Hellowork — scraping HTML
├── frontend/
│   ├── index.html        # SPA : auth + dashboard (Supabase JS v2)
│   └── vercel.json       # Config Vercel
├── supabase/
│   └── schema.sql        # Tables PostgreSQL + RLS — à exécuter dans Supabase
├── .env.example          # Template variables d'environnement
├── .gitignore
├── render.yaml           # Config déploiement Render
├── requirements.txt
└── run.sh                # Lancement local
```

---

## Variables d'environnement — Récapitulatif complet

### Backend (`.env` local + Render Dashboard)

| Variable | Où la trouver | Obligatoire |
|----------|---------------|:-----------:|
| `DATABASE_URL` | Supabase → Settings → Database → Connection string | ✅ |
| `SUPABASE_URL` | Supabase → Settings → API → Project URL | ✅ |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase → Settings → API → Publishable key | ✅ |

### Frontend (`frontend/index.html` — bloc CONFIG)

| Champ CONFIG | Valeur |
|--------------|--------|
| `SUPABASE_URL` | Même que ci-dessus |
| `SUPABASE_PUBLISHABLE_KEY` | Même que ci-dessus |
| `API_URL` | URL Render (ex: `https://job-hunter-api.onrender.com`) |

> La publishable key est **publique** — c'est normal de la mettre dans le HTML.

---

## API

Toutes les routes requièrent `Authorization: Bearer <JWT>` (sauf `/health`).

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/jobs` | Offres avec statut de l'utilisateur |
| GET | `/api/stats` | Compteurs par statut |
| POST | `/api/status` | Créer/modifier le statut d'une offre |
| GET | `/api/settings` | Paramètres de recherche |
| PUT | `/api/settings` | Modifier les paramètres |
| POST | `/api/scrape/start` | Lancer le scraping (background) |
| GET | `/api/scrape/status` | État du scraping en cours |
| GET | `/api/history` | Historique des recherches |
| GET | `/health` | Healthcheck (public) |
| GET | `/debug/scrapers` | Test scrapers sans sauvegarde |

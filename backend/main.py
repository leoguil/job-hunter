import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .database import engine, get_db, Base
from .models import Job, JobStatus, UserSettings, SearchRun
from .schemas import (
    JobOut, StatusUpdate, StatusOut,
    SettingsOut, SettingsUpdate,
    StatsOut, SearchRunOut,
)
from .auth import get_current_user_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Crée les tables si elles n'existent pas (utile pour SQLite en dev local)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Hunter API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hunt-inky.vercel.app",
        # Previews Vercel (ex: https://hunt-abc123.vercel.app)
        "https://*.vercel.app",
        # Dev local
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://hunt.*\.vercel\.app",
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

# ── Scrape state (par user) ───────────────────────────────────
# { user_id: { running, last_run, last_result, error } }
_scrape_status: Dict[str, dict] = {}


def _get_user_status(user_id: str) -> dict:
    return _scrape_status.setdefault(user_id, {
        "running": False,
        "last_run": None,
        "last_result": None,
        "error": None,
    })


# ── Background scrape ─────────────────────────────────────────

def _run_scrape(user_id: str):
    from .scrapers import wttj, hellowork
    from .database import SessionLocal

    status = _get_user_status(user_id)
    status["running"] = True
    status["error"] = None

    db = SessionLocal()
    try:
        settings = db.query(UserSettings).get(user_id)
        if not settings:
            settings = UserSettings(user_id=user_id)
            db.add(settings)
            db.commit()
            db.refresh(settings)

        mots_cles  = settings.mots_cles or ["business developer"]
        locs       = settings.localisation or []
        max_days   = settings.date_max or 30
        exclus     = [k.lower() for k in (settings.mots_cles_exclus or [])]

        all_jobs = []
        for scraper in [wttj, hellowork]:
            try:
                jobs = scraper.scrape(mots_cles, locs, max_days)
                logger.info(f"[{user_id[:8]}] {scraper.__name__}: {len(jobs)} jobs")
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error(f"[{user_id[:8]}] {scraper.__name__} failed: {e}", exc_info=True)

        # Filtre mots-clés exclus
        if exclus:
            all_jobs = [
                j for j in all_jobs
                if not any(kw in f"{j['titre']} {j.get('description','')}".lower() for kw in exclus)
            ]

        # Sauvegarde (dédupliqué)
        new_count = 0
        for jd in all_jobs:
            exists = (
                db.query(Job).filter(Job.url == jd["url"]).first()
                or db.query(Job).filter(Job.hash_unique == jd["hash_unique"]).first()
            )
            if exists:
                continue
            db.add(Job(
                titre=jd["titre"],
                entreprise=jd["entreprise"],
                localisation=jd.get("localisation"),
                salaire=jd.get("salaire"),
                date_publication=jd["date_publication"],
                description=jd.get("description"),
                url=jd["url"],
                source=jd["source"],
                hash_unique=jd["hash_unique"],
                date_scraping=datetime.now(timezone.utc),
            ))
            new_count += 1

        db.commit()

        # Historique
        run = SearchRun(
            user_id=user_id,
            nombre_resultats=len(all_jobs),
            nouveaux=new_count,
            mots_cles=mots_cles,
        )
        db.add(run)
        db.commit()

        result = {
            "total_scraped": len(all_jobs),
            "new": new_count,
            "duplicates": len(all_jobs) - new_count,
        }
        status["last_result"] = result
        status["last_run"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{user_id[:8]}] Scrape terminé: {result}")

    except Exception as e:
        status["error"] = str(e)
        logger.error(f"[{user_id[:8]}] Scrape échoué: {e}", exc_info=True)
    finally:
        db.close()
        status["running"] = False


# ── Helpers ───────────────────────────────────────────────────

def _get_or_create_settings(db: Session, user_id: str) -> UserSettings:
    s = db.query(UserSettings).get(user_id)
    if not s:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _enrich_jobs_with_status(jobs: List[Job], user_id: str, db: Session) -> List[dict]:
    """Ajoute le statut utilisateur à chaque job."""
    if not jobs:
        return []

    job_ids = [j.id for j in jobs]
    statuses = db.query(JobStatus).filter(
        JobStatus.user_id == user_id,
        JobStatus.job_id.in_(job_ids),
    ).all()
    status_map = {s.job_id: s for s in statuses}

    result = []
    for job in jobs:
        js = status_map.get(job.id)
        d = {
            "id": job.id,
            "titre": job.titre,
            "entreprise": job.entreprise,
            "localisation": job.localisation,
            "salaire": job.salaire,
            "date_publication": job.date_publication,
            "description": job.description,
            "url": job.url,
            "source": job.source,
            "date_scraping": job.date_scraping,
            "statut": js.statut if js else None,
            "notes": js.notes if js else None,
            "date_action": js.date_action if js else None,
        }
        result.append(d)
    return result


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

# ── Jobs ──────────────────────────────────────────────────────

@app.get("/api/jobs", response_model=List[JobOut])
def list_jobs(
    search: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    days: Optional[int]   = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    q = db.query(Job).order_by(Job.date_publication.desc())

    if search:
        term = f"%{search.lower()}%"
        q = q.filter(or_(
            Job.titre.ilike(term),
            Job.entreprise.ilike(term),
            Job.localisation.ilike(term),
        ))
    if source:
        q = q.filter(Job.source == source)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = q.filter(Job.date_publication >= cutoff)

    jobs = q.all()

    # Filtre par statut (côté applicatif pour simplicité)
    enriched = _enrich_jobs_with_status(jobs, user_id, db)

    if statut:
        if statut == "sans_statut":
            enriched = [j for j in enriched if j["statut"] is None]
        else:
            enriched = [j for j in enriched if j["statut"] == statut]

    return enriched


# ── Statuts ───────────────────────────────────────────────────

@app.post("/api/status", response_model=StatusOut)
def set_status(
    data: StatusUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    job = db.query(Job).get(data.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")

    existing = db.query(JobStatus).filter(
        JobStatus.user_id == user_id,
        JobStatus.job_id  == data.job_id,
    ).first()

    if existing:
        existing.statut      = data.statut
        existing.notes       = data.notes
        existing.date_action = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    js = JobStatus(
        user_id     = user_id,
        job_id      = data.job_id,
        statut      = data.statut,
        notes       = data.notes,
        date_action = datetime.now(timezone.utc),
    )
    db.add(js)
    db.commit()
    db.refresh(js)
    return js


# ── Stats ─────────────────────────────────────────────────────

@app.get("/api/stats", response_model=StatsOut)
def get_stats(
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    total     = db.query(func.count(Job.id)).scalar() or 0
    a_traiter = db.query(func.count(JobStatus.id)).filter(
        JobStatus.user_id == user_id, JobStatus.statut == "a_traiter"
    ).scalar() or 0
    postule   = db.query(func.count(JobStatus.id)).filter(
        JobStatus.user_id == user_id, JobStatus.statut == "postule"
    ).scalar() or 0
    ignore    = db.query(func.count(JobStatus.id)).filter(
        JobStatus.user_id == user_id, JobStatus.statut == "ignore"
    ).scalar() or 0

    return StatsOut(
        total=total,
        a_traiter=a_traiter,
        postule=postule,
        ignore=ignore,
        sans_statut=total - (a_traiter + postule + ignore),
    )


# ── Settings ──────────────────────────────────────────────────

@app.get("/api/settings", response_model=SettingsOut)
def get_settings(
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    return _get_or_create_settings(db, user_id)


@app.put("/api/settings", response_model=SettingsOut)
def update_settings(
    data: SettingsUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    s = _get_or_create_settings(db, user_id)
    s.mots_cles        = data.mots_cles
    s.localisation     = data.localisation
    s.salaire_min      = data.salaire_min
    s.date_max         = data.date_max
    s.mots_cles_exclus = data.mots_cles_exclus
    db.commit()
    db.refresh(s)
    return s


# ── Scraping ──────────────────────────────────────────────────

@app.post("/api/scrape/start")
def start_scrape(
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    status = _get_user_status(user_id)
    if status["running"]:
        return {"status": "already_running"}

    # Crée les settings si absents
    _get_or_create_settings(db, user_id)

    t = threading.Thread(target=_run_scrape, args=(user_id,), daemon=True)
    t.start()
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status(user_id: str = Depends(get_current_user_id)):
    return _get_user_status(user_id)


# ── Historique ────────────────────────────────────────────────

@app.get("/api/history", response_model=List[SearchRunOut])
def get_history(
    user_id: str = Depends(get_current_user_id),
    db: Session  = Depends(get_db),
):
    runs = (
        db.query(SearchRun)
        .filter(SearchRun.user_id == user_id)
        .order_by(SearchRun.date_run.desc())
        .limit(50)
        .all()
    )
    return runs


# ── Debug (dev uniquement) ────────────────────────────────────

@app.get("/debug/scrapers")
def debug_scrapers(
    keyword: str  = "business developer",
    location: str = "Lyon",
    days: int     = 30,
    user_id: str  = Depends(get_current_user_id),
):
    from .scrapers import wttj, hellowork
    report = {}
    for scraper, name in [(wttj, "wttj"), (hellowork, "hellowork")]:
        try:
            jobs = scraper.scrape([keyword], [location], max_days=days)
            report[name] = {
                "count": len(jobs),
                "sample": [{
                    "titre": j["titre"],
                    "entreprise": j["entreprise"],
                    "localisation": j.get("localisation"),
                    "date_publication": j["date_publication"].isoformat(),
                    "url": j["url"],
                } for j in jobs[:5]],
                "error": None,
            }
        except Exception as e:
            report[name] = {"count": 0, "sample": [], "error": str(e)}
    return report


# ── Healthcheck ───────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Serve frontend (mode monolithique — optionnel) ────────────
import os
if os.path.isdir("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

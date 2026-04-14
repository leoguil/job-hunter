from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Job ──────────────────────────────────────────────────────

class JobOut(BaseModel):
    id: int
    titre: str
    entreprise: str
    localisation: Optional[str] = None
    salaire: Optional[str] = None
    date_publication: datetime
    description: Optional[str] = None
    url: str
    source: str
    date_scraping: datetime
    # Statut de l'utilisateur courant (null si non défini)
    statut: Optional[str] = None
    notes: Optional[str] = None
    date_action: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Statut ───────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    job_id: int
    statut: str  # "a_traiter" | "postule" | "ignore"
    notes: Optional[str] = None


class StatusOut(BaseModel):
    id: int
    job_id: int
    statut: str
    date_action: datetime
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Settings ─────────────────────────────────────────────────

class SettingsOut(BaseModel):
    mots_cles: List[str]
    localisation: List[str]
    secteurs: List[str] = []
    salaire_min: Optional[int] = None
    date_max: int
    mots_cles_exclus: List[str]

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    mots_cles: List[str]
    localisation: List[str]
    secteurs: List[str] = []
    salaire_min: Optional[int] = None
    date_max: int = 30
    mots_cles_exclus: List[str] = []


# ── Stats ────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total: int
    a_traiter: int
    postule: int
    ignore: int
    sans_statut: int


# ── Historique ───────────────────────────────────────────────

class SearchRunOut(BaseModel):
    id: int
    date_run: datetime
    nombre_resultats: int
    nouveaux: int
    mots_cles: Optional[List[str]] = None

    model_config = {"from_attributes": True}

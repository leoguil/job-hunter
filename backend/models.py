from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime,
    Text, ForeignKey, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


class Job(Base):
    __tablename__ = "jobs"

    id               = Column(BigInteger, primary_key=True, index=True)
    titre            = Column(String, nullable=False)
    entreprise       = Column(String, nullable=False)
    localisation     = Column(String, nullable=True)
    salaire          = Column(String, nullable=True)
    date_publication = Column(DateTime(timezone=True), nullable=False)
    description      = Column(Text, nullable=True)
    url              = Column(String, unique=True, nullable=False)
    source           = Column(String, nullable=False)
    hash_unique      = Column(String, unique=True, nullable=False)
    date_scraping    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Lien vers la recherche qui a trouvé ce job (nullable : anciens jobs n'ont pas de lien)
    search_run_id    = Column(BigInteger, ForeignKey("search_runs.id", ondelete="SET NULL"), nullable=True, index=True)

    statuses = relationship("JobStatus", back_populates="job", lazy="dynamic")


class JobStatus(Base):
    """Statut d'un job pour un utilisateur donné."""
    __tablename__ = "job_status"

    id          = Column(BigInteger, primary_key=True, index=True)
    user_id     = Column(String, nullable=False, index=True)   # UUID Supabase
    job_id      = Column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    statut      = Column(String, nullable=False, default="a_traiter")
    date_action = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes       = Column(Text, nullable=True)

    job = relationship("Job", back_populates="statuses")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job"),
    )


class UserSettings(Base):
    """Paramètres de recherche par utilisateur."""
    __tablename__ = "user_settings"

    user_id          = Column(String, primary_key=True)
    mots_cles        = Column(JSON, default=lambda: ["développeur", "chef de projet"])
    localisation     = Column(JSON, default=lambda: ["Paris"])
    secteurs         = Column(JSON, default=lambda: [])   # ex: ["SaaS", "fintech"]
    salaire_min      = Column(Integer, nullable=True)
    date_max         = Column(Integer, default=30)
    mots_cles_exclus = Column(JSON, default=lambda: [])


class SearchRun(Base):
    """Historique des lancements de recherche par utilisateur."""
    __tablename__ = "search_runs"

    id               = Column(BigInteger, primary_key=True, index=True)
    user_id          = Column(String, nullable=False, index=True)
    date_run         = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    nombre_resultats = Column(Integer, default=0)
    nouveaux         = Column(Integer, default=0)
    mots_cles        = Column(JSON, nullable=True)

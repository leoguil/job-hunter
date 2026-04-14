"""
Harnais d'évaluation commun — mesure la qualité et la stabilité de chaque source.

Usage :
    python evaluator.py          # évalue toutes les sources enregistrées
    python evaluator.py remoteok # évalue une source spécifique
"""
from __future__ import annotations

import importlib
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Critères d'évaluation (poids) ──────────────────────────────────────────
WEIGHTS = {
    "scrapable_sans_auth": 30,
    "qualite_donnees":     25,
    "stabilite":           20,
    "richesse":            15,
    "difficulte":          10,
}

SOURCES = ["remoteok", "francetravail", "apec", "cadremploi"]


@dataclass
class EvalResult:
    source: str
    jobs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    latency_ms: float = 0.0

    # Scores individuels (0–100 chacun, pondérés ensuite)
    score_auth: float      = 0.0   # scrapable sans auth
    score_qualite: float   = 0.0   # qualité des champs
    score_stabilite: float = 0.0   # pas d'erreur, structure stable
    score_richesse: float  = 0.0   # champs bonus présents
    score_difficulte: float= 0.0   # facilité d'intégration

    @property
    def score_total(self) -> float:
        return (
            self.score_auth       * WEIGHTS["scrapable_sans_auth"] / 100
            + self.score_qualite  * WEIGHTS["qualite_donnees"]     / 100
            + self.score_stabilite* WEIGHTS["stabilite"]           / 100
            + self.score_richesse * WEIGHTS["richesse"]            / 100
            + self.score_difficulte*WEIGHTS["difficulte"]          / 100
        )


# ── Champs attendus ─────────────────────────────────────────────────────────
REQUIRED_FIELDS  = {"titre", "entreprise", "url", "date_publication"}
QUALITY_FIELDS   = {"localisation", "salaire", "date_publication"}
RICHNESS_FIELDS  = {"description", "secteur", "type_contrat"}


def _score_jobs(jobs: list[dict]) -> tuple[float, float]:
    """Retourne (score_qualite, score_richesse) de 0 à 100."""
    if not jobs:
        return 0.0, 0.0

    quality_hits  = 0
    richness_hits = 0

    for j in jobs:
        for f in QUALITY_FIELDS:
            if j.get(f):
                quality_hits += 1
        for f in RICHNESS_FIELDS:
            if j.get(f):
                richness_hits += 1

    quality_score  = 100 * quality_hits  / (len(jobs) * len(QUALITY_FIELDS))
    richness_score = 100 * richness_hits / (len(jobs) * len(RICHNESS_FIELDS))
    return round(quality_score, 1), round(richness_score, 1)


def evaluate_source(module_name: str) -> EvalResult:
    result = EvalResult(source=module_name)

    try:
        mod = importlib.import_module(f"backend.scrapers.poc.{module_name}")
    except ImportError:
        try:
            mod = importlib.import_module(module_name)
        except ImportError as exc:
            result.error = f"Import impossible : {exc}"
            return result

    fetch_fn: Callable | None = getattr(mod, "fetch_jobs", None)
    if fetch_fn is None:
        result.error = "Fonction fetch_jobs() introuvable dans le module"
        return result

    t0 = time.perf_counter()
    try:
        jobs = fetch_fn()
    except Exception as exc:
        result.error = str(exc)
        result.score_stabilite = 0.0
        result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return result

    result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    result.jobs = jobs or []

    # Stabilité : pas d'erreur + jobs récupérés
    result.score_stabilite = 100.0 if result.jobs else 20.0

    # Qualité + Richesse
    result.score_qualite, result.score_richesse = _score_jobs(result.jobs)

    # Auth / difficulté — lues depuis les métadonnées du module si présentes
    result.score_auth       = float(getattr(mod, "SCORE_AUTH",       100))
    result.score_difficulte = float(getattr(mod, "SCORE_DIFFICULTE", 100))

    return result


def print_report(results: list[EvalResult]) -> None:
    sep = "─" * 72
    print(f"\n{'JOB HUNTER — Rapport d'évaluation des sources':^72}")
    print(sep)
    print(f"{'Source':<16} {'Jobs':>5} {'Auth':>5} {'Qual':>5} {'Stab':>5} {'Rich':>5} {'Diff':>5} {'TOTAL':>6} {'Latence':>9}")
    print(sep)
    for r in sorted(results, key=lambda x: -x.score_total):
        status = "✅" if r.score_total >= 65 else ("⚠️ " if r.score_total >= 40 else "❌")
        if r.error:
            print(f"{r.source:<16}  ERREUR: {r.error[:50]}")
        else:
            print(
                f"{r.source:<16}"
                f" {len(r.jobs):>5}"
                f" {r.score_auth:>5.0f}"
                f" {r.score_qualite:>5.0f}"
                f" {r.score_stabilite:>5.0f}"
                f" {r.score_richesse:>5.0f}"
                f" {r.score_difficulte:>5.0f}"
                f" {r.score_total:>5.1f} {status}"
                f" {r.latency_ms:>7.0f}ms"
            )
    print(sep)
    print("Seuil recommandé pour intégration : ≥ 65 points\n")


if __name__ == "__main__":
    targets = sys.argv[1:] or SOURCES
    results = [evaluate_source(s) for s in targets]
    print_report(results)

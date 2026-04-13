"""
Welcome to the Jungle scraper — via Algolia API.

Credentials extraites depuis le HTML de WTTJ :
  ALGOLIA_APPLICATION_ID = CSEKHVMS53
  ALGOLIA_API_KEY_CLIENT  = 4bd8f6215d0cc52b26430765769e65a0
  Index                   = wttj_jobs_production_fr
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from .base import make_hash, is_within_days

logger = logging.getLogger(__name__)

ALGOLIA_APP_ID  = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX   = "wttj_jobs_production_fr"
ALGOLIA_URL     = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
WTTJ_BASE       = "https://www.welcometothejungle.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "Content-Type": "application/json",
    "Referer": "https://www.welcometothejungle.com/",
    "Origin": "https://www.welcometothejungle.com",
}


def _parse_date(raw) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        # Try full string first, then truncated versions
        candidates = [raw, raw[:26], raw[:19]]
        fmts = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
        ]
        for candidate in candidates:
            for fmt in fmts:
                try:
                    dt = datetime.strptime(candidate, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def _build_url(job: dict) -> Optional[str]:
    slug = job.get("slug", "")
    org = job.get("organization") or {}
    org_slug = org.get("slug", "") if isinstance(org, dict) else ""
    if slug and org_slug:
        return f"{WTTJ_BASE}/fr/companies/{org_slug}/jobs/{slug}"
    return None


def _normalize(hit: dict) -> Optional[dict]:
    titre = hit.get("name", "").strip()
    if not titre:
        return None

    org = hit.get("organization") or {}
    entreprise = (org.get("name", "") if isinstance(org, dict) else "").strip()

    # Location: offices list OR remote
    offices = hit.get("offices") or []
    localisation = ""
    if offices and isinstance(offices, list):
        cities = [o.get("city") or o.get("name", "") for o in offices if isinstance(o, dict)]
        localisation = ", ".join(filter(None, cities))
    remote = hit.get("remote") or ""
    if remote and isinstance(remote, str) and remote not in ("none", "no"):
        localisation = f"{localisation} ({remote})" if localisation else remote

    # Salary
    sal_min = hit.get("salary_minimum")
    sal_max = hit.get("salary_maximum")
    sal_cur = hit.get("salary_currency", "€")
    sal_per = hit.get("salary_period", "")
    salaire = None
    if sal_min or sal_max:
        period_map = {"yearly": "an", "monthly": "mois", "daily": "jour"}
        per_label = period_map.get(sal_per, sal_per)
        if sal_min and sal_max and sal_min != sal_max:
            salaire = f"{int(sal_min):,} – {int(sal_max):,} {sal_cur}/{per_label}".replace(",", " ")
        elif sal_min:
            salaire = f"{int(sal_min):,} {sal_cur}/{per_label}".replace(",", " ")

    date_pub = _parse_date(hit.get("published_at"))
    if not date_pub:
        return None

    url = _build_url(hit)
    if not url:
        return None

    return {
        "titre": titre,
        "entreprise": entreprise,
        "localisation": localisation,
        "salaire": salaire,
        "date_publication": date_pub,
        "description": (hit.get("summary") or "").strip(),
        "url": url,
        "source": "welcometothejungle",
        "hash_unique": make_hash(titre, entreprise, localisation),
    }


def scrape(mots_cles: List[str], localisations: List[str], max_days: int = 30) -> List[dict]:
    results = []
    seen_hashes = set()
    session = requests.Session()

    for keyword in mots_cles:
        logger.info(f"[WTTJ] Keyword: '{keyword}'")
        for page in range(0, 5):  # Algolia pages are 0-indexed
            payload = {
                "query": keyword,
                "hitsPerPage": 20,
                "page": page,
                "attributesToRetrieve": [
                    "name", "organization", "offices", "remote",
                    "published_at", "salary_minimum", "salary_maximum",
                    "salary_currency", "salary_period", "slug", "summary",
                    "contract_type",
                ],
            }

            # Add location filter via facets (aroundQuery not supported by this key)
            facet_filters = []
            if localisations:
                loc = localisations[0]
                if loc.lower() in ("remote", "télétravail", "full_remote"):
                    facet_filters.append(["remote:fulltime"])
                else:
                    # Filter by city — supports OR logic (multiple cities)
                    city_filters = [f"offices.city:{city}" for city in localisations
                                    if city.lower() not in ("remote", "télétravail")]
                    if city_filters:
                        facet_filters.append(city_filters)  # OR between cities

            if facet_filters:
                payload["facetFilters"] = facet_filters

            try:
                resp = session.post(ALGOLIA_URL, headers=HEADERS, json=payload, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[WTTJ] Algolia request failed (page {page}): {e}")
                break

            hits = data.get("hits", [])
            nb_pages = data.get("nbPages", 1)
            logger.info(f"[WTTJ] Page {page}: {len(hits)} hits (total: {data.get('nbHits', '?')})")

            if not hits:
                break

            valid_on_page = 0
            old_on_page = 0

            for hit in hits:
                job = _normalize(hit)
                if not job:
                    continue
                if not is_within_days(job["date_publication"], max_days):
                    old_on_page += 1
                    continue
                h = job["hash_unique"]
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                results.append(job)
                valid_on_page += 1

            logger.info(f"[WTTJ] Page {page}: {valid_on_page} valid, {old_on_page} trop anciens")

            # Stop early if we've seen too many old jobs
            if old_on_page > len(hits) * 0.7:
                logger.info("[WTTJ] Trop d'offres trop anciennes, arrêt")
                break

            if page >= nb_pages - 1:
                break

            time.sleep(0.8)

    logger.info(f"[WTTJ] Total collecté : {len(results)} offres")
    return results

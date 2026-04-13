"""
Hellowork scraper — parsing HTML server-side.

Structure HTML confirmée :
  <ul class="tw-grid tw-grid-cols-1 tw-gap-6 ...">
    <li>
      <div data-id-storage-item-id="OFFER_ID">
        <input name="title"   value="..."/>
        <input name="company" value="..."/>
        <a href="/fr-fr/emplois/ID.html">...</a>
        text parts: [titre, entreprise, (Super recruteur?), localisation, contrat, (salaire?), (remote?), "Voir l'offre", date]
      </div>
    </li>
  </ul>
"""

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from .base import HEADERS, make_hash, is_within_days

logger = logging.getLogger(__name__)

HELLOWORK_BASE   = "https://www.hellowork.com"
HELLOWORK_SEARCH = "https://www.hellowork.com/fr-fr/emploi/recherche.html"

SKIP_PARTS = {"super recruteur", "voir l'offre", "voir l offre", "télétravail complet", "télétravail partiel", "nouveau"}


def _parse_date_fr(raw: str) -> Optional[datetime]:
    """Parse French relative or absolute dates."""
    if not raw:
        return None
    raw = raw.lower().strip()
    now = datetime.now(timezone.utc)

    if any(x in raw for x in ("aujourd", "maintenant", "heure", "minute", "seconde", "instant")):
        return now
    if "hier" in raw:
        return now - timedelta(days=1)

    m = re.search(r"il y a\s+(\d+)\s*(jour|semaine|mois)", raw)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "jour":
            return now - timedelta(days=n)
        if unit == "semaine":
            return now - timedelta(weeks=n)
        if unit == "mois":
            return now - timedelta(days=n * 30)

    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            s = raw[:len(fmt)]
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # "Il y a X jours" without accent
    m2 = re.search(r"(\d+)\s*j(?:our)?s?", raw)
    if m2:
        return now - timedelta(days=int(m2.group(1)))

    return None


def _extract_salary(parts: List[str]) -> Optional[str]:
    for p in parts:
        if "€" in p:
            return p.strip()
    return None


def _extract_location(parts: List[str], titre: str, entreprise: str) -> str:
    skip = {titre.lower(), entreprise.lower(), "voir l'offre"} | SKIP_PARTS
    for p in parts:
        pl = p.lower()
        if pl in skip:
            continue
        if "€" in p:
            continue
        # Location usually has a dash + department number or "Lyon", "Paris", etc.
        if re.search(r" - \d{2}|\blyon\b|\bparis\b|\bmarseille\b|\bnantes\b|\bbordeaux\b|\blille\b|\btoulouse\b|\bremote\b|\bdistanciel\b", pl):
            return p.strip()
        # "75", "69", city pattern
        if re.search(r"^\w[\w\s]+ - \d{2,3}$", p.strip()):
            return p.strip()
    return ""


def _parse_card(li) -> Optional[dict]:
    """Parse a single <li> job card."""
    try:
        title_input   = li.find("input", {"name": "title"})
        company_input = li.find("input", {"name": "company"})
        link          = li.find("a", href=True)

        titre     = (title_input.get("value", "") if title_input else "").strip()
        entreprise = (company_input.get("value", "") if company_input else "").strip()
        href      = link.get("href", "") if link else ""

        if not titre or not href:
            return None

        url = href if href.startswith("http") else f"{HELLOWORK_BASE}{href}"

        # All non-empty text parts
        raw_parts = [t.strip() for t in li.get_text(separator="|||").split("|||") if t.strip()]

        # Date is the last part before/after "Voir l'offre"
        date_raw = ""
        for p in reversed(raw_parts):
            pl = p.lower()
            if pl not in SKIP_PARTS and "€" not in p and p not in (titre, entreprise):
                date_raw = p
                break
        date_pub = _parse_date_fr(date_raw)
        if not date_pub:
            return None

        localisation = _extract_location(raw_parts, titre, entreprise)
        salaire      = _extract_salary(raw_parts)

        return {
            "titre": titre,
            "entreprise": entreprise,
            "localisation": localisation,
            "salaire": salaire,
            "date_publication": date_pub,
            "description": "",
            "url": url,
            "source": "hellowork",
            "hash_unique": make_hash(titre, entreprise, localisation),
        }
    except Exception as e:
        logger.debug(f"[HW] Erreur parsing card: {e}")
        return None


def _fetch_page(session: requests.Session, keyword: str, location: str, page: int) -> Optional[BeautifulSoup]:
    params = {
        "k": keyword,
        "st": "date",
        "p": page,
    }
    if location:
        params["l"] = location

    url = f"{HELLOWORK_SEARCH}?{urlencode(params)}"
    logger.info(f"[HW] Fetching: {url}")

    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.error(f"[HW] Fetch failed ({url}): {e}")
        return None


def _get_job_list(soup: BeautifulSoup):
    """Return the <ul> containing job <li> cards."""
    ul = soup.find("ul", class_=lambda c: c and "tw-grid-cols-1" in c and "tw-gap-6" in c)
    if ul:
        return ul.find_all("li", recursive=False)

    # Fallback: any li with a data-id-storage-item-id parent
    candidates = soup.find_all("div", attrs={"data-id-storage-item-id": True})
    return [c.find_parent("li") or c for c in candidates if c]


def _has_next_page(soup: BeautifulSoup) -> bool:
    return bool(
        soup.find("a", rel="next")
        or soup.find("a", attrs={"aria-label": lambda v: v and "suivante" in v.lower()})
        or soup.find(attrs={"data-cy": "nextPage"})
    )


def scrape(mots_cles: List[str], localisations: List[str], max_days: int = 30) -> List[dict]:
    results = []
    seen_hashes = set()
    session = requests.Session()
    location = localisations[0] if localisations else ""

    for keyword in mots_cles:
        logger.info(f"[HW] Keyword: '{keyword}', location: '{location}'")

        for page in range(1, 6):
            soup = _fetch_page(session, keyword, location, page)
            if not soup:
                break

            cards = _get_job_list(soup)
            logger.info(f"[HW] Page {page}: {len(cards)} cartes trouvées")

            if not cards:
                logger.warning(f"[HW] Aucune carte trouvée page {page} — structure HTML peut-être modifiée")
                break

            valid_on_page = 0
            old_on_page = 0

            for li in cards:
                job = _parse_card(li)
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

            logger.info(f"[HW] Page {page}: {valid_on_page} valides, {old_on_page} trop anciens")

            if old_on_page > len(cards) * 0.7:
                logger.info("[HW] Trop d'offres anciennes, arrêt")
                break

            if not _has_next_page(soup):
                break

            time.sleep(1.2)

    logger.info(f"[HW] Total collecté : {len(results)} offres")
    return results

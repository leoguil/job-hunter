"""
RemoteOK — scraper production.

Source : flux RSS public https://remoteok.com/remote-jobs.rss
Auth   : aucune
Offres : remote worldwide, principalement anglophone
Fraîcheur : ~95 offres, < 30 jours en général

Note technique : RemoteOK utilise des champs XML non-standard (hors spec RSS 2.0)
    <company>   → nom de l'entreprise
    <tags>      → tags comma-separated
    <location>  → localisation (état/pays US, ou vide pour full-remote)
Ces champs ne sont pas récupérables via findtext("category").
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List
from urllib.request import Request, urlopen

from .base import make_hash, is_within_days

logger = logging.getLogger(__name__)

RSS_URL = "https://remoteok.com/remote-jobs.rss"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobHunterBot/1.0)",
    "Accept":     "application/rss+xml, application/xml, text/xml",
}


def _parse_date(raw: str) -> datetime:
    """Parse ISO 8601 ou RFC 2822 → datetime UTC."""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def scrape(mots_cles: List[str], localisations: List[str], max_days: int = 30) -> List[dict]:
    """
    Interface identique aux scrapers WTTJ et Hellowork.

    - mots_cles   : filtrés côté client sur titre + tags + description
    - localisations: ignoré (RemoteOK = remote worldwide uniquement)
    - max_days    : filtre les offres trop anciennes
    """
    logger.info("[RemoteOK] Récupération du flux RSS…")

    try:
        req = Request(RSS_URL, headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except Exception as exc:
        logger.error("[RemoteOK] Impossible de récupérer le RSS: %s", exc)
        return []

    try:
        root    = ET.fromstring(raw)
        channel = root.find("channel")
        items   = channel.findall("item") if channel is not None else []
    except Exception as exc:
        logger.error("[RemoteOK] Erreur parsing XML: %s", exc)
        return []

    logger.info("[RemoteOK] %d items dans le feed", len(items))

    results   = []
    seen_hashes = set()

    for item in items:
        titre       = (item.findtext("title")    or "").strip()
        lien        = (item.findtext("link")     or "").strip()
        pub_date    = (item.findtext("pubDate")  or "").strip()
        desc        = (item.findtext("description") or "").strip()
        entreprise  = (item.findtext("company")  or "").strip()
        tags_raw    = (item.findtext("tags")     or "").strip()
        location_raw= (item.findtext("location") or "").strip()

        if not titre or not lien:
            continue

        date_pub = _parse_date(pub_date)

        if not is_within_days(date_pub, max_days):
            continue

        tags         = [t.strip() for t in tags_raw.split(",") if t.strip()]
        localisation = location_raw or "Remote"

        # Filtre par mot-clé (titre + tags + description)
        if mots_cles:
            haystack = f"{titre} {tags_raw} {desc}".lower()
            if not any(kw.lower() in haystack for kw in mots_cles):
                continue

        h = make_hash(titre, entreprise, localisation)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        results.append({
            "titre":            titre,
            "entreprise":       entreprise or "N/A",
            "localisation":     localisation,
            "salaire":          None,
            "date_publication": date_pub,
            "description":      desc[:500] if desc else "",
            "url":              lien,
            "source":           "remoteok",
            "hash_unique":      h,
        })

    logger.info("[RemoteOK] %d offres après filtres (mots_cles=%s, max_days=%d)",
                len(results), mots_cles, max_days)
    return results

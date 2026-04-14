"""
RemoteOK — flux RSS public.
Méthode  : GET https://remoteok.com/remote-jobs.rss
Auth     : Aucune
Score auth estimé : 100 / Difficulté estimée : 100 (très simple)

Usage autonome :
    python remoteok.py [keyword]
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

# Métadonnées pour l'évaluateur
SCORE_AUTH       = 100   # pas d'auth requise
SCORE_DIFFICULTE = 100   # RSS standard

RSS_URL = "https://remoteok.com/remote-jobs.rss"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobHunterBot/1.0)",
    "Accept":     "application/rss+xml, application/xml, text/xml",
}


def fetch_jobs(keyword: str | None = None, limit: int = 50) -> list[dict]:
    """
    Retourne une liste de jobs depuis le flux RSS de RemoteOK.

    Note : RemoteOK utilise des tags XML non-standard (hors namespace RSS) :
        <company>   — nom de l'entreprise (PAS dans le titre)
        <tags>      — tags comma-separated
        <location>  — localisation (état/pays, ou vide pour full-remote)
    Ces champs ne sont pas récupérables via findtext("category").

    Chaque dict contient au minimum :
        titre, entreprise, url, date_publication
    Et optionnellement :
        description, tags (liste), salaire, localisation
    """
    req = Request(RSS_URL, headers=HEADERS)
    with urlopen(req, timeout=15) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        return []

    jobs: list[dict] = []
    for item in channel.findall("item"):
        titre     = (item.findtext("title") or "").strip()
        lien      = (item.findtext("link")  or "").strip()
        pub_date  = item.findtext("pubDate") or ""
        desc_html = item.findtext("description") or ""

        # Champs non-standard RemoteOK (tags XML hors namespace RSS)
        entreprise  = (item.findtext("company")  or "").strip()
        tags_raw    = (item.findtext("tags")      or "").strip()
        location_raw= (item.findtext("location")  or "").strip()

        # Parse date — RemoteOK utilise ISO 8601, pas RFC 2822
        try:
            date_pub = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            try:
                date_pub = parsedate_to_datetime(pub_date).astimezone(timezone.utc)
            except Exception:
                date_pub = datetime.now(timezone.utc)

        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        localisation = location_raw or "Remote"

        job = {
            "titre":            titre,
            "entreprise":       entreprise or "N/A",
            "url":              lien,
            "date_publication": date_pub.isoformat(),
            "description":      desc_html[:1000] if desc_html else None,
            "localisation":     localisation,
            "source":           "remoteok",
            "tags":             tags,
            "salaire":          None,
            "secteur":          tags[0] if tags else None,
            "type_contrat":     "Remote",
        }

        if keyword:
            haystack = f"{job['titre']} {tags_raw} {job.get('description', '')}".lower()
            if keyword.lower() not in haystack:
                continue

        jobs.append(job)
        if len(jobs) >= limit:
            break

    return jobs


# ── Exécution autonome ──────────────────────────────────────────────────────
if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    results = fetch_jobs(keyword=kw, limit=10)
    print(f"RemoteOK — {len(results)} jobs trouvés\n")
    for j in results:
        print(f"  [{j['date_publication'][:10]}] {j['titre']} @ {j['entreprise']}")
        print(f"    {j['url']}")
        if j.get("tags"):
            print(f"    Tags : {', '.join(j['tags'][:5])}")
        print()

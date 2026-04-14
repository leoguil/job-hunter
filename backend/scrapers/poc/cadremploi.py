"""
Cadremploi — scraping HTML.
URL cible : https://www.cadremploi.fr/emploi/liste_offres.html

Auth     : Aucune (User-Agent requis pour éviter le blocage 403)
Score auth estimé : 90 (pas d'auth, mais structure HTML instable)
Difficulté        : 50 (HTML scraping, risque de changements structurels)

⚠️  Ce module est classé PRIORITÉ BASSE (score ~55).
     Préférer RemoteOK, France Travail ou APEC si disponibles.

Usage autonome :
    python cadremploi.py [keyword]
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Métadonnées pour l'évaluateur
SCORE_AUTH       = 90   # pas d'auth mais User-Agent strict
SCORE_DIFFICULTE = 50   # HTML scraping instable

BASE_URL   = "https://www.cadremploi.fr"
SEARCH_URL = BASE_URL + "/emploi/liste_offres.html"
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml",
}

# ── Parser HTML minimal ──────────────────────────────────────────────────────
class _OffreParser(HTMLParser):
    """
    Extrait les offres Cadremploi depuis le HTML de la page de résultats.
    Structure ciblée (peut changer) :
        <article class="offer-item ...">
            <h2 class="offer-title"><a href="...">Titre</a></h2>
            <span class="offer-company">...</span>
            <span class="offer-location">...</span>
            <time datetime="2024-01-15">...</time>
        </article>
    """

    def __init__(self) -> None:
        super().__init__()
        self._jobs: list[dict] = []
        self._current: dict | None = None
        self._in_title  = False
        self._in_company= False
        self._in_loc    = False
        self._in_anchor = False
        self._depth     = 0

    # -- helpers
    def _cls(self, attrs: list) -> str:
        for k, v in attrs:
            if k == "class":
                return v or ""
        return ""

    def _attr(self, attrs: list, name: str) -> str:
        for k, v in attrs:
            if k == name:
                return v or ""
        return ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        cls = self._cls(attrs)

        if tag == "article" and "offer-item" in cls:
            self._current = {"titre": "", "entreprise": "", "localisation": None,
                             "url": "", "date_publication": "", "salaire": None,
                             "source": "cadremploi", "description": None,
                             "secteur": None, "type_contrat": None}
            self._depth = 0
            return

        if self._current is None:
            return

        if tag == "h2" and "offer-title" in cls:
            self._in_title = True
        if tag == "a" and self._in_title:
            href = self._attr(attrs, "href")
            if href:
                self._current["url"] = href if href.startswith("http") else BASE_URL + href
            self._in_anchor = True
        if tag == "span" and "offer-company" in cls:
            self._in_company = True
        if tag == "span" and "offer-location" in cls:
            self._in_loc = True
        if tag == "time":
            dt = self._attr(attrs, "datetime")
            if dt and self._current:
                try:
                    d = datetime.fromisoformat(dt).astimezone(timezone.utc)
                    self._current["date_publication"] = d.isoformat()
                except Exception:
                    self._current["date_publication"] = datetime.now(timezone.utc).isoformat()

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self._current:
            if self._current.get("titre") and self._current.get("url"):
                if not self._current.get("date_publication"):
                    self._current["date_publication"] = datetime.now(timezone.utc).isoformat()
                self._jobs.append(self._current)
            self._current = None
            self._in_title = self._in_company = self._in_loc = self._in_anchor = False
        if tag == "h2":
            self._in_title  = False
            self._in_anchor = False
        if tag == "a" and self._in_anchor:
            self._in_anchor = False
        if tag == "span":
            self._in_company = False
            self._in_loc     = False

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = data.strip()
        if not text:
            return
        if self._in_anchor and self._in_title:
            self._current["titre"] += text
        elif self._in_company:
            self._current["entreprise"] += text
        elif self._in_loc:
            self._current["localisation"] = (self._current.get("localisation") or "") + text

    @property
    def jobs(self) -> list[dict]:
        return self._jobs


def _parse_relative_date(text: str) -> str:
    """Convertit 'il y a 3 jours' en datetime ISO."""
    now = datetime.now(timezone.utc)
    m = re.search(r"(\d+)\s*jour", text, re.I)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*heure", text, re.I)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()
    return now.isoformat()


def fetch_jobs(keyword: str = "développeur", limit: int = 50) -> list[dict]:
    """
    Retourne des offres Cadremploi en scrapant le HTML.
    ⚠️  Fragile — structure HTML sujette aux changements.
    """
    params = urllib.parse.urlencode({"q": keyword, "nbResultats": min(limit, 50)})
    url    = f"{SEARCH_URL}?{params}"
    req    = Request(url, headers=HEADERS)

    try:
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"Cadremploi HTTP {exc.code}: {exc.reason}") from exc

    parser = _OffreParser()
    parser.feed(html)
    jobs = parser.jobs[:limit]

    # Nettoyage des champs
    for j in jobs:
        j["titre"]      = j["titre"].strip()
        j["entreprise"] = j["entreprise"].strip() or "N/A"
        if j.get("localisation"):
            j["localisation"] = j["localisation"].strip()

    return jobs


# ── Exécution autonome ──────────────────────────────────────────────────────
if __name__ == "__main__":
    kw = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "développeur"
    try:
        results = fetch_jobs(keyword=kw, limit=10)
        print(f"Cadremploi — {len(results)} offres pour « {kw} »\n")
        if not results:
            print("  Aucun résultat — la structure HTML a peut-être changé.")
        for j in results:
            print(f"  [{j['date_publication'][:10]}] {j['titre']} @ {j['entreprise']}")
            if j.get("localisation"):
                print(f"    {j['localisation']}")
            print(f"    {j['url']}")
            print()
    except RuntimeError as e:
        print(f"[ERREUR] {e}")
        sys.exit(1)

"""
APEC — API Algolia non officielle (même pattern que Welcome to the Jungle).
Endpoint Algolia extrait du HTML de apec.fr.

Auth     : Clé Algolia publique (extraite du source apec.fr — peut changer)
Score auth estimé : 80 (clé publique, mais non officielle → risque)
Difficulté        : 80 (même pattern qu'Algolia/WTTJ)

Usage autonome :
    python apec.py [keyword]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Métadonnées pour l'évaluateur
SCORE_AUTH       = 80
SCORE_DIFFICULTE = 80

# Clés Algolia extraites du HTML apec.fr (publiques, sans inscription)
# ⚠️  Ces clés peuvent changer si APEC met à jour leur front-end.
ALGOLIA_APP_ID   = "9HKTNRK0RM"
ALGOLIA_API_KEY  = "f2d7e7ecee0d28459e2d2a4dea3eb29e"
ALGOLIA_INDEX    = "offres-emploi"

SEARCH_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
    f"/1/indexes/{ALGOLIA_INDEX}/query"
)

HEADERS = {
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-API-Key":        ALGOLIA_API_KEY,
    "Content-Type":             "application/json",
    "User-Agent":               "Mozilla/5.0 (compatible; JobHunterBot/1.0)",
}


def _parse_hit(hit: dict) -> dict:
    """Mappe un hit Algolia APEC vers le format interne."""
    # Date de publication (timestamp Unix ou chaîne ISO)
    raw_date = hit.get("datePublication") or hit.get("dateCreation") or ""
    date_pub: datetime
    if isinstance(raw_date, (int, float)):
        date_pub = datetime.fromtimestamp(raw_date / 1000, tz=timezone.utc)
    elif raw_date:
        try:
            date_pub = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except Exception:
            date_pub = datetime.now(timezone.utc)
    else:
        date_pub = datetime.now(timezone.utc)

    # Localisation
    lieu = hit.get("lieux") or hit.get("lieu") or {}
    if isinstance(lieu, list):
        lieu = lieu[0] if lieu else {}
    localisation = lieu.get("libelle") or lieu.get("ville") or hit.get("lieuTravail")

    # Salaire
    remun = hit.get("remunerationLibelle") or hit.get("salaire")

    # URL canonique
    slug = hit.get("urlOffre") or hit.get("objectID") or ""
    url  = f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/{slug}" if slug else ""

    return {
        "titre":            (hit.get("titre") or hit.get("intitule") or "").strip(),
        "entreprise":       (hit.get("nomSociete") or hit.get("entreprise") or "N/A").strip(),
        "url":              url,
        "date_publication": date_pub.isoformat(),
        "description":      (hit.get("texteHtml") or hit.get("description") or "")[:1000],
        "localisation":     localisation,
        "salaire":          remun,
        "source":           "apec",
        "secteur":          hit.get("secteurActivite") or hit.get("secteur"),
        "type_contrat":     hit.get("typeContrat"),
    }


def fetch_jobs(keyword: str = "chef de projet", limit: int = 50) -> list[dict]:
    """
    Retourne des offres APEC via l'index Algolia public.
    Lève RuntimeError si l'API renvoie une erreur HTTP.
    """
    payload = json.dumps({
        "query":          keyword,
        "hitsPerPage":    min(limit, 100),
        "page":           0,
        "attributesToRetrieve": [
            "titre", "intitule", "nomSociete", "entreprise",
            "datePublication", "dateCreation",
            "lieux", "lieu", "lieuTravail",
            "remunerationLibelle", "salaire",
            "texteHtml", "description",
            "secteurActivite", "secteur",
            "typeContrat", "urlOffre", "objectID",
        ],
    }).encode()

    req = Request(SEARCH_URL, data=payload, headers=HEADERS, method="POST")
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"APEC Algolia HTTP {exc.code}: {body[:200]}") from exc

    hits = data.get("hits", [])
    return [_parse_hit(h) for h in hits]


# ── Exécution autonome ──────────────────────────────────────────────────────
if __name__ == "__main__":
    kw = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "chef de projet"
    try:
        results = fetch_jobs(keyword=kw, limit=10)
        print(f"APEC — {len(results)} offres pour « {kw} »\n")
        for j in results:
            sal = f" | {j['salaire']}" if j.get("salaire") else ""
            print(f"  [{j['date_publication'][:10]}] {j['titre']} @ {j['entreprise']}")
            print(f"    {j.get('localisation', 'N/A')}{sal}")
            print(f"    {j['url']}")
            print()
    except RuntimeError as e:
        print(f"[ERREUR] {e}")
        print("Note : les clés Algolia APEC sont extraites du front-end et peuvent changer.")
        sys.exit(1)

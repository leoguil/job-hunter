"""
France Travail (ex Pôle Emploi) — API REST officielle OAuth2.
Endpoint : https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search

Auth     : OAuth2 client_credentials
             → https://francetravail.io/data/api/offres-emploi
             → Inscription gratuite sur francetravail.io/partenaire
Score auth estimé : 60 (inscription gratuite mais nécessaire)
Difficulté        : 60 (OAuth2 + codes ROME à mapper)

Variables d'environnement :
    FT_CLIENT_ID     — identifiant client obtenu après inscription
    FT_CLIENT_SECRET — secret client

Usage autonome :
    FT_CLIENT_ID=xxx FT_CLIENT_SECRET=yyy python francetravail.py "développeur python"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Métadonnées pour l'évaluateur
SCORE_AUTH       = 60   # inscription gratuite mais obligatoire
SCORE_DIFFICULTE = 60   # OAuth2 + mapping ROME

TOKEN_URL  = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE      = "api_offresdemploiv2 o2dsoffre"


def _get_token(client_id: str, client_secret: str) -> str:
    """Récupère un token OAuth2 via client_credentials."""
    payload = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
        "scope":         SCOPE,
    }).encode()

    req = Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["access_token"]


def _parse_offre(offre: dict) -> dict:
    """Mappe une offre France Travail vers le format interne."""
    # Date de création
    date_str = offre.get("dateCreation", "")
    try:
        date_pub = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        date_pub = datetime.now(timezone.utc)

    # Salaire
    salaire = None
    if offre.get("salaire"):
        sal = offre["salaire"]
        salaire = sal.get("libelle") or sal.get("commentaire")

    # Localisation
    lieu = offre.get("lieuTravail", {})
    localisation = lieu.get("libelle") or lieu.get("codePostal")

    # Type contrat
    type_contrat = offre.get("typeContratLibelle") or offre.get("typeContrat")

    # Secteur (via code NAF libellé ou domaine)
    secteur = None
    if offre.get("secteurActiviteLibelle"):
        secteur = offre["secteurActiviteLibelle"]
    elif offre.get("domaine"):
        secteur = offre["domaine"]

    return {
        "titre":            offre.get("intitule", "").strip(),
        "entreprise":       (offre.get("entreprise") or {}).get("nom", "N/A").strip(),
        "url":              offre.get("origineOffre", {}).get("urlOrigine", ""),
        "date_publication": date_pub.isoformat(),
        "description":      (offre.get("description") or "")[:1000],
        "localisation":     localisation,
        "salaire":          salaire,
        "source":           "francetravail",
        "secteur":          secteur,
        "type_contrat":     type_contrat,
        "ref_ft":           offre.get("id"),
    }


def fetch_jobs(
    keyword: str = "développeur",
    localisation: str | None = None,
    limit: int = 50,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> list[dict]:
    """
    Retourne des offres France Travail pour le mot-clé donné.
    Lit FT_CLIENT_ID / FT_CLIENT_SECRET depuis l'environnement si non fournis.
    Lève RuntimeError si les credentials sont absents.
    """
    cid = client_id or os.getenv("FT_CLIENT_ID", "")
    csecret = client_secret or os.getenv("FT_CLIENT_SECRET", "")

    if not cid or not csecret:
        raise RuntimeError(
            "France Travail : FT_CLIENT_ID et FT_CLIENT_SECRET requis.\n"
            "Inscription gratuite sur https://francetravail.io/data/api/offres-emploi"
        )

    token = _get_token(cid, csecret)

    params: dict[str, str] = {
        "motsCles":  keyword,
        "range":     f"0-{min(limit, 149) - 1}",
        "sort":      "1",  # tri par date
    }
    if localisation:
        params["commune"] = localisation

    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
    })

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        raise RuntimeError(f"France Travail API HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"France Travail API unreachable: {exc.reason}") from exc

    offres = data.get("resultats", [])
    return [_parse_offre(o) for o in offres]


# ── Exécution autonome ──────────────────────────────────────────────────────
if __name__ == "__main__":
    kw = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "développeur python"
    try:
        results = fetch_jobs(keyword=kw, limit=10)
        print(f"France Travail — {len(results)} offres pour « {kw} »\n")
        for j in results:
            sal = f" | {j['salaire']}" if j.get("salaire") else ""
            print(f"  [{j['date_publication'][:10]}] {j['titre']} @ {j['entreprise']}")
            print(f"    {j.get('localisation', 'N/A')}{sal}")
            print(f"    {j['url']}")
            print()
    except RuntimeError as e:
        print(f"[ERREUR] {e}")
        sys.exit(1)

"""
Authentification via l'API Supabase Auth.

Stratégie : au lieu de valider le JWT localement (ce qui nécessite SUPABASE_JWT_SECRET),
on demande directement à Supabase de vérifier le token.
→ Aucun secret côté backend requis.
→ Compatible avec tous les projets Supabase (anciens et nouveaux formats de clé).

Variables d'environnement requises :
  SUPABASE_URL             — ex: https://xxxx.supabase.co
  SUPABASE_PUBLISHABLE_KEY — clé publique (anon / publishable)
"""

import hashlib
import logging
import os
import time

import requests as _requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
security = HTTPBearer()

# ── Config ────────────────────────────────────────────────────
_SUPABASE_URL            = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

# ── Cache token → user_id (TTL 5 min) ────────────────────────
# Évite d'appeler Supabase à chaque requête HTTP.
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300  # secondes


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:24]


def _cache_get(token: str) -> str | None:
    entry = _cache.get(_digest(token))
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _cache.pop(_digest(token), None)
    return None


def _cache_set(token: str, user_id: str) -> None:
    _cache[_digest(token)] = (user_id, time.monotonic() + _CACHE_TTL)


# ── Dependency FastAPI ────────────────────────────────────────

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Valide le Bearer token JWT auprès de Supabase Auth et retourne le user_id.
    Injecte cette dépendance dans chaque route protégée.
    """
    if not _SUPABASE_URL or not _SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL ou SUPABASE_PUBLISHABLE_KEY non configuré côté serveur",
        )

    token = credentials.credentials

    # 1. Vérifier le cache d'abord
    cached_id = _cache_get(token)
    if cached_id:
        return cached_id

    # 2. Vérifier auprès de Supabase
    try:
        resp = _requests.get(
            f"{_SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": _SUPABASE_PUBLISHABLE_KEY,
            },
            timeout=6,
        )
    except _requests.RequestException as exc:
        logger.error("Supabase auth unreachable: %s", exc)
        raise HTTPException(status_code=503, detail="Service d'authentification indisponible")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    if resp.status_code != 200:
        logger.warning("Supabase auth returned %s: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=401, detail="Échec de vérification du token")

    user_id: str = resp.json().get("id", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID introuvable")

    _cache_set(token, user_id)
    return user_id

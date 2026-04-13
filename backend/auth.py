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

def validate_token(token: str) -> tuple[str, dict]:
    """
    Valide le token auprès de Supabase.
    Retourne (user_id, debug_info).
    Lève HTTPException si invalide.
    """
    token_prefix = token[:20] + "..."

    if not _SUPABASE_URL or not _SUPABASE_PUBLISHABLE_KEY:
        logger.error("SUPABASE_URL ou SUPABASE_PUBLISHABLE_KEY non définis")
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL ou SUPABASE_PUBLISHABLE_KEY non configuré côté serveur",
        )

    logger.info("Validating token %s against %s/auth/v1/user", token_prefix, _SUPABASE_URL)

    try:
        resp = _requests.get(
            f"{_SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": _SUPABASE_PUBLISHABLE_KEY,
            },
            timeout=8,
        )
    except _requests.RequestException as exc:
        logger.error("Supabase auth unreachable for token %s: %s", token_prefix, exc)
        raise HTTPException(status_code=503, detail=f"Service auth indisponible: {exc}")

    logger.info("Supabase returned HTTP %s for token %s", resp.status_code, token_prefix)

    if resp.status_code == 401:
        body = resp.text[:300]
        logger.warning("Supabase 401 for token %s: %s", token_prefix, body)
        raise HTTPException(
            status_code=401,
            detail=f"Token invalide ou expiré (Supabase 401: {body})",
        )

    if resp.status_code != 200:
        body = resp.text[:300]
        logger.error("Supabase unexpected %s for token %s: %s", resp.status_code, token_prefix, body)
        raise HTTPException(
            status_code=401,
            detail=f"Échec vérification token (Supabase {resp.status_code}: {body})",
        )

    data = resp.json()
    user_id: str = data.get("id", "")
    if not user_id:
        logger.error("Supabase returned 200 but no user id: %s", str(data)[:200])
        raise HTTPException(status_code=401, detail="User ID introuvable dans la réponse Supabase")

    logger.info("Token OK — user_id: %s", user_id)
    return user_id, data


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Valide le Bearer token JWT auprès de Supabase Auth et retourne le user_id.
    Injecte cette dépendance dans chaque route protégée.
    """
    token = credentials.credentials

    # 1. Cache d'abord (évite un appel réseau à chaque requête)
    cached_id = _cache_get(token)
    if cached_id:
        logger.debug("Token cache hit — user_id: %s", cached_id)
        return cached_id

    # 2. Validation distante
    user_id, _ = validate_token(token)
    _cache_set(token, user_id)
    return user_id

"""
Registre des scrapers de production.

Pour activer/désactiver une source : passer `enabled` à True/False.
Pour limiter le nombre d'offres par source : ajuster `limit`.

Résumé des choix :
  wttj       — Algolia non officielle, fiable, FR ✅ intégré
  hellowork  — HTML scraping, fiable, FR ✅ intégré
  remoteok   — RSS public, fiable, Remote worldwide ✅ intégré
  apec       — Algolia non officielle, clés instables  ⏳ POC seulement
  ft         — API officielle, credentials OAuth2 requis ⏳ POC seulement
  cadremploi — HTML scraping, URL/structure instable ❌ exclu
"""
from __future__ import annotations

from typing import TypedDict


class SourceConfig(TypedDict):
    name:    str
    module:  str
    enabled: bool
    limit:   int   # max offres retournées par ce scraper (0 = illimité)


# ── Registre ───────────────────────────────────────────────────────────────
# L'ordre détermine la priorité de déduplication.
SOURCES: list[SourceConfig] = [
    {
        "name":    "wttj",
        "module":  "wttj",
        "enabled": True,
        "limit":   200,
    },
    {
        "name":    "hellowork",
        "module":  "hellowork",
        "enabled": True,
        "limit":   200,
    },
    {
        "name":    "remoteok",
        "module":  "remoteok",
        "enabled": True,
        "limit":   100,
        # Offres remote en anglais — utile pour dev/tech, moins pour autres secteurs
    },
    # Sources POC non encore intégrées :
    # {"name": "apec",   "module": "apec",          "enabled": False, "limit": 100},
    # {"name": "ft",     "module": "francetravail",  "enabled": False, "limit": 100},
]

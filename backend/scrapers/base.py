import hashlib
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


def make_hash(titre: str, entreprise: str, localisation: str) -> str:
    raw = f"{titre.lower().strip()}|{entreprise.lower().strip()}|{(localisation or '').lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_within_days(date: datetime, max_days: int) -> bool:
    now = datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return (now - date).days <= max_days


def fetch_page(url: str, session: Optional[requests.Session] = None, retries: int = 3) -> Optional[BeautifulSoup]:
    s = session or requests.Session()
    for attempt in range(retries):
        try:
            resp = s.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def fetch_json(url: str, session: Optional[requests.Session] = None, retries: int = 3, **kwargs) -> Optional[dict]:
    s = session or requests.Session()
    for attempt in range(retries):
        try:
            resp = s.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def post_json(url: str, payload: dict, headers_extra: dict = None, session: Optional[requests.Session] = None, retries: int = 3) -> Optional[dict]:
    s = session or requests.Session()
    h = {**HEADERS, "Accept": "application/json", "Content-Type": "application/json"}
    if headers_extra:
        h.update(headers_extra)
    for attempt in range(retries):
        try:
            resp = s.post(url, json=payload, headers=h, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

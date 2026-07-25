#!/usr/bin/env python
"""fetch_biznesradar.py -- WSE-only supplemental data from biznesradar.pl.

Scrapes the FREE blocks of the biznesradar.pl profile page for a Warsaw-listed
name and returns the fields Yahoo/yfinance frequently leaves ``null`` for ``.WA``
tickers: the Piotroski F-Score, the Altman EM-Score, and the market-value ratios
(C/Z, C/WK, C/P, C/ZO) plus ROE / ROA.

biznesradar has no public API, so this is an HTML scrape of the public profile
page. Only free fields are read (EBITDA / EV are premium-gated and skipped).

Ticker mapping: Yahoo ``DIA.WA`` -> biznesradar ``DIA`` (strip the ``.WA``
suffix). This holds for the common WSE names but is not guaranteed for every
listing; pass the bare biznesradar code if it differs.

SSL: honours ``REQUESTS_CA_BUNDLE`` / ``CURL_CA_BUNDLE`` / ``SSL_CERT_FILE``
(needed behind corporate TLS inspection), otherwise the system trust store.

Usage:
    python scripts/fetch_biznesradar.py DIA.WA
    python scripts/fetch_biznesradar.py KRU.WA --no-cache
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import emit  # noqa: E402

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - deps ship with yfinance
    requests = None
    BeautifulSoup = None

BASE_URL = "https://www.biznesradar.pl/notowania/{code}"
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "biznesradar"
)
DEFAULT_CACHE_TTL = 12 * 3600  # seconds; biznesradar data lags ~1 quarter anyway
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# biznesradar market-value ratio label -> our field name. Longest labels first
# so "C/ZO" is matched before the "C/Z" prefix.
RATIO_LABELS = {
    "C/ZO": "p_ebit",
    "C/WK": "pb",
    "C/Z": "pe",
    "C/P": "ps",
    "ROE": "roe_pct",
    "ROA": "roa_pct",
}
_RATIO_ORDER = sorted(RATIO_LABELS, key=len, reverse=True)

# Altman EM-Score letter grade -> 0-100 financial-health score (higher = safer).
# The EM-Score maps Altman's Z''-score onto a synthetic bond rating.
ALTMAN_HEALTH = {
    "AAA": 100, "AA": 92, "A": 84, "BBB": 72,
    "BB": 60, "B": 45, "CCC": 30, "CC": 20, "C": 12, "D": 0,
}


def to_code(symbol: str) -> str:
    """Map a Yahoo-style WSE ticker to its biznesradar code (DIA.WA -> DIA)."""
    s = symbol.strip().upper()
    return s[:-3] if s.endswith(".WA") else s


def _num(text):
    """Parse a biznesradar cell ('9.15', '43.22%', '-0.05\u00a0>~sector*') to float or None."""
    if text is None:
        return None
    t = text.replace("\u00a0", " ").replace("%", "")
    m = re.search(r"-?\d+(?:[.,]\d+)?", t)
    return float(m.group().replace(",", ".")) if m else None


def _int(text):
    v = _num(text)
    return int(v) if v is not None else None


def _cell_num(cell):
    """Numeric value from a ``td`` cell, reading its ``span.pv`` to avoid label noise."""
    if cell is None:
        return None
    pv = cell.select_one("span.pv") or cell
    return _num(pv.get_text(strip=True))


def _altman_health(grade):
    """Map an Altman EM-Score letter grade (e.g. 'BB', 'A-') to a 0-100 score."""
    if not grade:
        return None
    base = grade.rstrip("+-")
    score = ALTMAN_HEALTH.get(base)
    if score is None:
        return None
    if grade.endswith("+"):
        score = min(100, score + 4)
    elif grade.endswith("-"):
        score = max(0, score - 4)
    return score


def _resolve_verify():
    """Return a CA-bundle path from the usual env vars, else True (system store)."""
    for var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        path = os.environ.get(var)
        if path and os.path.exists(path):
            return path
    return True


def parse_ratings(soup) -> dict:
    """Read Piotroski F-Score and Altman EM-Score from the OCENA block."""
    out = {"piotroski_f_score": None, "altman_score": None, "altman_health_score": None}
    box = soup.select_one("div.element.ratings")
    if not box:
        return out
    for tr in box.select("tr"):
        name_td = tr.select_one("td.name")
        val = tr.select_one("td.value span.pv")
        if not name_td or not val:
            continue
        label = name_td.get_text(" ", strip=True).lower()
        text = val.get_text(strip=True)
        if "piotroski" in label:
            out["piotroski_f_score"] = _int(text)
        elif "altman" in label:
            grade = text.strip().upper() or None
            out["altman_score"] = grade
            out["altman_health_score"] = _altman_health(grade)
    return out


def parse_ratios(soup):
    """Read market-value ratios + ROE/ROA (value and sector delta) from WSKAZNIKI."""
    out = {v: None for v in RATIO_LABELS.values()}
    vs_sector = {}
    box = soup.select_one("div.element.ratios")
    if not box:
        return out, vs_sector
    for tr in box.select("tr"):
        name_td = tr.select_one("td.name")
        if not name_td:
            continue
        label = name_td.get_text("", strip=True).upper()
        key = next((RATIO_LABELS[l] for l in _RATIO_ORDER if label.startswith(l)), None)
        if not key:
            continue
        cells = tr.select("td.value")
        plain = next((c for c in cells if "sector" not in (c.get("class") or [])), None)
        sect = next((c for c in cells if "sector" in (c.get("class") or [])), None)
        out[key] = _cell_num(plain)
        delta = _cell_num(sect)
        if delta is not None:
            vs_sector[key] = delta
    return out, vs_sector


def parse_report_period(soup):
    """Extract the reporting period (e.g. '2026/Q1') from a block disclaimer."""
    for sel in ("div.element.ratings", "div.element.ratios"):
        box = soup.select_one(sel)
        if not box:
            continue
        disc = box.select_one(".disclaimer")
        if disc:
            m = re.search(r"raport\s+(\d{4}/Q\d|\d{4})", disc.get_text(" ", strip=True), re.I)
            if m:
                return m.group(1)
    return None


def _cache_path(code: str) -> str:
    return os.path.join(CACHE_DIR, f"{code}.json")


def _read_cache(code: str, ttl: int):
    path = _cache_path(code)
    if not os.path.exists(path) or time.time() - os.path.getmtime(path) > ttl:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_cache(code: str, payload: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(code), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def fetch_html(code: str, timeout: int = 30) -> tuple[str, str]:
    """GET the biznesradar profile page; fix charset if the server omits it."""
    url = BASE_URL.format(code=code)
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
        verify=_resolve_verify(),
        timeout=timeout,
    )
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text, url


def collect(symbol: str, use_cache: bool = True, cache_ttl: int = DEFAULT_CACHE_TTL) -> dict:
    """Fetch + parse the free biznesradar fields for one WSE symbol."""
    code = to_code(symbol)
    warnings: list[str] = []
    if not symbol.strip().upper().endswith(".WA") and "." in symbol:
        warnings.append("biznesradar covers Warsaw (WSE) listings; a non-.WA symbol may not resolve.")

    if use_cache:
        cached = _read_cache(code, cache_ttl)
        if cached is not None:
            cached["cached"] = True
            return cached

    html, url = fetch_html(code)
    soup = BeautifulSoup(html, "html.parser")
    ratings = parse_ratings(soup)
    ratios, vs_sector = parse_ratios(soup)
    period = parse_report_period(soup)

    if ratings["piotroski_f_score"] is None and all(v is None for v in ratios.values()):
        warnings.append(
            "No biznesradar fields parsed -- page layout may have changed or the code is wrong."
        )

    payload = {
        "symbol": symbol.strip().upper(),
        "biznesradar_code": code,
        "source_url": url,
        "report_period": period,
        "piotroski_f_score": ratings["piotroski_f_score"],
        "altman_score": ratings["altman_score"],
        "altman_health_score": ratings["altman_health_score"],
        "pe": ratios["pe"],
        "pb": ratios["pb"],
        "ps": ratios["ps"],
        "p_ebit": ratios["p_ebit"],
        "roe_pct": ratios["roe_pct"],
        "roa_pct": ratios["roa_pct"],
        "vs_sector_median": vs_sector,
        "cached": False,
        "fetched_at": int(time.time()),
        "warnings": warnings,
        "web_search_terms": [
            f"{code} akcje wyniki finansowe",
            f"{code} GPW analiza wskazniki",
        ],
        "note": (
            "Free biznesradar fields only (EBITDA/EV are premium). Piotroski F-Score (0-9) "
            "feeds the quality pillar; Altman EM-Score (altman_health_score 0-100) feeds risk; "
            "ratios/ROE/ROA are .WA fallbacks when yfinance is null. Data lags ~1 quarter "
            "(see report_period)."
        ),
    }
    if use_cache:
        _write_cache(code, payload)
    return payload


def main() -> None:
    if requests is None or BeautifulSoup is None:
        raise SystemExit("Missing deps. Run: pip install requests beautifulsoup4")
    p = argparse.ArgumentParser(description="Scrape free biznesradar.pl fields for a WSE ticker.")
    p.add_argument("symbol", help="Yahoo-style ticker, e.g. DIA.WA (or a bare biznesradar code)")
    p.add_argument("--no-cache", action="store_true", help="Bypass the local cache and refetch")
    p.add_argument("--cache-ttl", type=int, default=DEFAULT_CACHE_TTL,
                   help="Cache freshness window in seconds (default 12h)")
    args = p.parse_args()
    emit(collect(args.symbol, use_cache=not args.no_cache, cache_ttl=args.cache_ttl))


if __name__ == "__main__":
    main()

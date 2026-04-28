"""FRED (Federal Reserve Economic Data) client — free, no key required."""

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://api.stlouisfed.org/fred"

# Common FRED series IDs
SERIES = {
    "dxy":        "DTWEXBGS",   # Trade-weighted USD index
    "cpi":        "CPIAUCSL",   # CPI all items
    "core_cpi":   "CPILFESL",   # CPI less food and energy
    "fed_funds":  "FEDFUNDS",   # Effective fed funds rate
    "t10y2y":     "T10Y2Y",     # 10yr minus 2yr (yield curve)
    "gold":       "GOLDAMGBD228NLBM",  # Gold price USD
    "vix":        "VIXCLS",     # CBOE VIX
    "m2":         "M2SL",       # M2 money supply
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_series(series_id: str, limit: int = 12) -> list[dict]:
    """Latest `limit` observations for a FRED series."""
    params = {
        "series_id": series_id,
        "sort_order": "desc",
        "limit": limit,
        "file_type": "json",
    }
    resp = requests.get(f"{BASE_URL}/series/observations", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("observations", [])


def get_dollar_index() -> dict:
    obs = get_series(SERIES["dxy"], limit=2)
    return {"series": "DXY", "latest": obs[0] if obs else {}, "prev": obs[1] if len(obs) > 1 else {}}


def get_inflation_data() -> dict:
    cpi = get_series(SERIES["cpi"], limit=13)
    core = get_series(SERIES["core_cpi"], limit=13)
    return {"cpi": cpi[:2], "core_cpi": core[:2]}


def get_yield_curve() -> dict:
    obs = get_series(SERIES["t10y2y"], limit=5)
    return {"t10y2y": obs}


def get_fed_funds_rate() -> dict:
    obs = get_series(SERIES["fed_funds"], limit=3)
    return {"fed_funds_rate": obs}


def get_m2() -> dict:
    obs = get_series(SERIES["m2"], limit=6)
    return {"m2": obs}

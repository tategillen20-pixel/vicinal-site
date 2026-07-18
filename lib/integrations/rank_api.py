"""
Wrapper functions for a keyword rank-tracking API. Live mode uses DataForSEO's
SERP API.

Stub mode returns randomized, realistic-looking data with no network calls.
"""
import os
import random
from datetime import datetime, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from lib.db import db

# "stub" (default) returns randomized, realistic-looking rank data so agent
# logic can be tested before signing up for a real rank-tracking provider.
# "live" calls the real DataForSEO API below. Switch via the RANK_API_MODE
# env var -- no code change needed to flip between them.
RANK_API_MODE = os.environ.get("RANK_API_MODE", "stub").strip().lower()

DATAFORSEO_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"

# DataForSEO's location_name must match their locations database exactly,
# which spells out the full state name (e.g. "Austin,Texas,United States") --
# clients.state in our schema stores the two-letter abbreviation, so it needs
# translating before being sent.
US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def _location_name(city, state):
    if not city or not state:
        return "United States"
    state_name = US_STATE_NAMES.get(state.strip().upper(), state)
    return f"{city},{state_name},United States"


def _now():
    # Microsecond precision matters here: two checks run back-to-back
    # (e.g. while testing) would otherwise land in the same whole second and
    # get collapsed into one point by the dashboard's history chart.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _stub_check_ranking(business_name, keyword, city, state):
    if random.random() < 0.15:
        # ~15% of checks come back "not found in top 20" -- realistic for a
        # small local business on a competitive keyword.
        return {
            "keyword": keyword,
            "position": None,
            "found_business_name": None,
            "checked_at": _now(),
        }
    return {
        "keyword": keyword,
        "position": random.randint(1, 20),
        "found_business_name": business_name,
        "checked_at": _now(),
    }


def _log_rank_api_error(business_name, keyword, error_detail):
    try:
        db.insert_activity_log(
            agent_name="rank_api",
            client_id=None,
            action="rank_check_failed",
            detail=f"Live rank check failed for '{keyword}' ({business_name}): {error_detail}",
        )
    except Exception:
        # A logging failure shouldn't crash the caller on top of the
        # original API failure.
        pass


def _find_business_rank(items, business_name):
    business_name_lower = (business_name or "").lower()

    # Prefer a Local Pack (map pack) match -- that's what matters most for
    # local search visibility -- and fall back to a plain organic match.
    for wanted_type in ("local_pack", "organic"):
        for item in items:
            if item.get("type") != wanted_type:
                continue
            title = (item.get("title") or "").lower()
            if business_name_lower and business_name_lower in title:
                return item
    return None


def _live_check_ranking(business_name, keyword, city, state):
    # DataForSEO SERP API -- Google Organic, "Live Advanced" endpoint.
    # Docs: https://docs.dataforseo.com/v3/serp/google/organic/live/advanced/
    # This is their synchronous "Live" task type (billed per call, simplest
    # to integrate) as opposed to the cheaper async Task POST/GET flow --
    # worth switching to that if per-keyword costs matter at scale. Local
    # Pack (map pack) results appear inline in the same "items" list with
    # "type": "local_pack" when Google shows one for this keyword.
    checked_at = _now()
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")

    if not login or not password:
        _log_rank_api_error(business_name, keyword, "DATAFORSEO_LOGIN/DATAFORSEO_PASSWORD not set")
        return {"keyword": keyword, "position": None, "found_business_name": None, "checked_at": checked_at}

    payload = [
        {
            "keyword": keyword,
            "location_name": _location_name(city, state),
            "language_code": "en",
            "device": "mobile",
            "depth": 20,
        }
    ]

    try:
        response = requests.post(DATAFORSEO_ENDPOINT, auth=(login, password), json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        task = data["tasks"][0]
        if task.get("status_code") != 20000:
            raise ValueError(f"DataForSEO task error: {task.get('status_message')}")

        items = task["result"][0].get("items") or []
    except Exception as exc:
        _log_rank_api_error(business_name, keyword, str(exc))
        return {"keyword": keyword, "position": None, "found_business_name": None, "checked_at": checked_at}

    match = _find_business_rank(items, business_name)
    if match is None:
        return {"keyword": keyword, "position": None, "found_business_name": None, "checked_at": checked_at}

    return {
        "keyword": keyword,
        "position": match.get("rank_absolute"),
        "found_business_name": match.get("title"),
        "checked_at": checked_at,
    }


def check_ranking(business_name, keyword, city, state):
    if RANK_API_MODE == "live":
        return _live_check_ranking(business_name, keyword, city, state)
    return _stub_check_ranking(business_name, keyword, city, state)

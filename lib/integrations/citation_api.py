"""
Wrapper for NAP (Name-Address-Phone) consistency checks across online
business directories (Yelp, Bing Places, Facebook, Apple Maps, etc).

Stubs only — no real checks yet.
"""
import os
import random

# "stub" (default) returns randomized, realistic-looking results so agent
# logic can be tested before signing up for a real citation-checking
# service. "real" calls the live check below. Switch via the
# CITATION_API_MODE env var -- no code change needed once wired up.
CITATION_API_MODE = os.environ.get("CITATION_API_MODE", "stub").strip().lower()


def _stub_check_citation(business_name, address, phone, source):
    roll = random.random()

    if roll < 0.15:
        return {
            "source": source,
            "found_name": None,
            "found_address": None,
            "found_phone": None,
            "match_status": "not_found",
        }

    if roll < 0.35:
        # Simulate a realistic real-world inconsistency.
        mismatch_kind = random.choice(["address_abbr", "missing_suite", "old_phone"])
        found_name = business_name
        found_address = address
        found_phone = phone
        if mismatch_kind == "address_abbr":
            found_address = (address or "").replace("Street", "St.").replace("Avenue", "Ave.")
        elif mismatch_kind == "missing_suite":
            found_address = (address or "").split(",")[0]
        elif mismatch_kind == "old_phone":
            found_phone = "555-0100"
        return {
            "source": source,
            "found_name": found_name,
            "found_address": found_address,
            "found_phone": found_phone,
            "match_status": "mismatched",
        }

    return {
        "source": source,
        "found_name": business_name,
        "found_address": address,
        "found_phone": phone,
        "match_status": "matched",
    }


def _real_check_citation(business_name, address, phone, source):
    # TODO: call a real citation-checking provider instead of the stub above.
    #
    # Two realistic options, with a real tradeoff:
    # - A paid citation API (Moz Local, BrightLocal): more reliable for
    #   production -- they already maintain the scraping/API relationships
    #   with each directory and absorb the compliance burden.
    # - A custom per-directory scraper: cheaper, but fragile (each
    #   directory's HTML/layout can change without notice) and may violate
    #   that directory's terms of service -- not recommended beyond a quick
    #   prototype.
    #
    # Must return the same shape as the stub above:
    # {source, found_name, found_address, found_phone, match_status}.
    raise NotImplementedError


def check_citation(business_name, address, phone, source):
    if CITATION_API_MODE == "real":
        return _real_check_citation(business_name, address, phone, source)
    return _stub_check_citation(business_name, address, phone, source)

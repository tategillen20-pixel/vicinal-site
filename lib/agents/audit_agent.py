"""
audit_agent.py

Generates a free prospect audit for sales purposes -- runs BEFORE a business
has given us any GBP access, so it only uses public data (rank + citation
checks) plus a couple of manually-entered observations about their live
listing. Nothing here writes to rankings/citations (those require a real
client_id); the gathered data lives only in the audits table.
"""
import json
import os
import sys

from openai import OpenAI

from lib.db import db
from lib.integrations import citation_api, rank_api

AGENT_NAME = "audit_agent"
MODEL = "gpt-4o-mini"

# Same fixed source list as citation_agent.SOURCES in the main seo-agent
# project. Inlined here rather than importing that whole file, since nothing
# else in citation_agent.py (its run()/summary logic) is needed for audits.
CITATION_SOURCES = ["Yelp", "Bing Places", "Facebook", "Apple Maps"]

# --- Prompt (edit freely to tune tone/style) ---
SYSTEM_PROMPT = (
    "You are writing a short, friendly audit summary for a prospective "
    "client who has not yet signed up for any services, based on the "
    "structured public data gathered about their online presence. Follow "
    "these rules strictly:\n"
    "- Only report findings directly supported by the gathered data below. "
    "Never invent findings or numbers that aren't present in the data.\n"
    "- Never guarantee specific results -- do not promise a specific "
    "ranking or outcome (e.g. do not say 'we'll get you to #1').\n"
    "- Frame findings as opportunities, not criticism -- e.g. write "
    "'there's room to improve visibility' rather than 'your profile is "
    "bad' or similar negative framing.\n"
    "- Keep it short: 3-5 sentences total.\n"
    "- End with a soft call-to-action inviting them to learn more about "
    "ongoing management -- not a hard sell.\n"
    "- Write plain prose only -- no Markdown formatting."
)

USER_PROMPT_TEMPLATE = (
    "Business name: {business_name}\n"
    "Location: {city}, {state}\n\n"
    "Audit data (the only facts you may reference):\n{audit_data_json}\n\n"
    "Write the audit summary."
)
# --- end prompt ---


def gather_audit_data(prospect_id, keywords, manual_observations):
    prospect = db.get_prospect_by_id(prospect_id)
    if prospect is None:
        raise ValueError(f"No prospect found with id {prospect_id}")

    keyword_results = [
        {
            "keyword": keyword,
            "position": rank_api.check_ranking(
                prospect["business_name"], keyword, prospect["city"], prospect["state"]
            )["position"],
        }
        for keyword in keywords
    ]

    citation_results = [
        {
            "source": source,
            "match_status": citation_api.check_citation(
                prospect["business_name"], prospect["address"], prospect["phone"], source
            )["match_status"],
        }
        for source in CITATION_SOURCES
    ]

    return {
        "prospect_id": prospect_id,
        "business_name": prospect["business_name"],
        "city": prospect["city"],
        "state": prospect["state"],
        "rankings": {
            "keywords": keyword_results,
        },
        "citations": {
            "sources_checked": len(citation_results),
            "matched_count": sum(1 for c in citation_results if c["match_status"] == "matched"),
            "mismatched_count": sum(1 for c in citation_results if c["match_status"] == "mismatched"),
            "not_found_count": sum(1 for c in citation_results if c["match_status"] == "not_found"),
            "details": citation_results,
        },
        "manual_observations": manual_observations,
    }


def _generate_summary(business_name, city, state, audit_data):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        business_name=business_name,
        city=city,
        state=state,
        audit_data_json=json.dumps(audit_data, indent=2),
    )
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def generate_audit(prospect_id, keywords, manual_observations):
    prospect = db.get_prospect_by_id(prospect_id)
    if prospect is None:
        raise ValueError(f"No prospect found with id {prospect_id}")

    audit_data = gather_audit_data(prospect_id, keywords, manual_observations)
    summary_text = _generate_summary(
        prospect["business_name"], prospect["city"], prospect["state"], audit_data
    )

    audit_id = db.insert_audit(
        prospect_id=prospect_id,
        summary_text=summary_text,
        audit_data=json.dumps(audit_data),
    )
    db.update_prospect_status(prospect_id, "completed")
    db.insert_activity_log(
        agent_name=AGENT_NAME,
        client_id=None,
        action="generated_audit",
        detail=f"Created audit {audit_id} for prospect {prospect_id} ({prospect['business_name']})",
    )

    return audit_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 -m lib.agents.audit_agent <prospect_id> <keyword1,keyword2,...>")
        sys.exit(1)

    new_audit_id = generate_audit(int(sys.argv[1]), sys.argv[2].split(","), {})
    print(f"Created audit {new_audit_id}")

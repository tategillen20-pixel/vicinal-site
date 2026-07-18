"""
Wrapper for sending the generated audit summary via Resend's API.
Docs: https://resend.com/docs/api-reference/emails/send-email
"""
import html
import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"


def send_audit_email(to_email, business_name, audit_summary_text):
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL")

    if not api_key or not from_email:
        raise RuntimeError("RESEND_API_KEY/RESEND_FROM_EMAIL not set")

    subject = f"Your free local search audit for {business_name}"
    html_body = (
        "<p>" + html.escape(audit_summary_text).replace("\n", "</p><p>") + "</p>"
        "<p>— Vicinal</p>"
    )

    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": audit_summary_text,
            "html": html_body,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()

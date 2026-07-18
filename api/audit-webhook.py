"""
api/audit-webhook.py

Vercel Python serverless function. Receives a Formspree webhook when a
prospect submits the free-audit request form, runs an automated audit using
only public data, emails the result via Resend, and updates prospect status.
Routed at /api/audit-webhook.

Formspree's webhook payload shape (confirmed from their docs):
{
  "form": "<form id>",
  "keys": ["business_name", "email", "city", ...],
  "submission": {
    "_date": "...",
    "business_name": "...",
    "email": "...",
    "city": "...",
    ...
  }
}
"""
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.agents.audit_agent import generate_audit
from lib.db import db
from lib.integrations.email_api import send_audit_email


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0) or 0)
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_body.decode("utf-8"))
            submission = payload.get("submission", {})

            business_name = (submission.get("business_name") or "").strip()
            email = (submission.get("email") or "").strip()
            city = (submission.get("city") or "").strip() or None

            if not business_name or not email:
                self._send_json(400, {"error": "business_name and email are required"})
                return

            prospect_id = db.insert_prospect(
                business_name=business_name,
                city=city,
                contact_email=email,
                source="website_form",
            )

            # No real target keywords come in from the form yet -- default
            # to the business name itself as a reasonable single keyword.
            keywords = [business_name]
            audit_id = generate_audit(prospect_id, keywords, {})

            audit = db.get_audits_by_prospect_id(prospect_id)[-1]
            send_audit_email(email, business_name, audit["summary_text"])

            db.update_prospect_status(prospect_id, "sent")
            db.insert_activity_log(
                agent_name="audit_webhook",
                client_id=None,
                action="sent_audit_email",
                detail=f"Audit {audit_id} emailed to {email} for prospect {prospect_id}",
            )

            self._send_json(200, {"status": "ok", "prospect_id": prospect_id, "audit_id": audit_id})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"error": str(exc)})

    def _send_json(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

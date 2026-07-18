"""
One-off local test: simulates a real Formspree webhook POST hitting
api/audit-webhook.py, with the DB/LLM/email calls mocked out so this makes
zero real network calls and costs nothing. Verifies the handler correctly
parses Formspree's payload shape and returns a clean 200 JSON response.

Run from the project root:
    python3 test_webhook_mock.py
"""
import importlib.util
import io
import json
import sys
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

# api/audit-webhook.py has a hyphen in its name, so it can't be imported with
# a normal `import` statement -- load it by file path instead, the same way
# Vercel's runtime loads it.
spec = importlib.util.spec_from_file_location("audit_webhook", "api/audit-webhook.py")
audit_webhook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_webhook)

fake_formspree_payload = json.dumps(
    {
        "form": "abc123",
        "keys": ["business_name", "email", "city"],
        "submission": {
            "_date": "2026-07-17T00:00:00",
            "business_name": "Test Biz",
            "email": "owner@testbiz.example",
            "city": "Lawrence",
        },
    }
).encode("utf-8")

# Build a handler instance without going through BaseHTTPRequestHandler's
# real socket-based __init__ -- fill in just enough of its normal internal
# state (requestline/client_address/etc) for send_response()'s logging to work.
h = audit_webhook.handler.__new__(audit_webhook.handler)
h.rfile = io.BytesIO(fake_formspree_payload)
h.headers = Message()
h.headers["Content-Length"] = str(len(fake_formspree_payload))
h.wfile = io.BytesIO()
h.client_address = ("127.0.0.1", 0)
h.requestline = "POST /api/audit-webhook HTTP/1.1"
h.request_version = "HTTP/1.1"
h.log_message = lambda *args, **kwargs: None

with patch.object(audit_webhook, "generate_audit", return_value=99) as mock_generate_audit, \
     patch.object(audit_webhook, "send_audit_email", return_value={"id": "email_123"}) as mock_send_email, \
     patch("lib.db.db.insert_prospect", return_value=42) as mock_insert_prospect, \
     patch("lib.db.db.get_audits_by_prospect_id", return_value=[{"summary_text": "Fake audit summary."}]), \
     patch("lib.db.db.update_prospect_status") as mock_update_status, \
     patch("lib.db.db.insert_activity_log") as mock_log:
    h.do_POST()

raw_response = h.wfile.getvalue().decode("utf-8")
status_line, _, rest = raw_response.partition("\r\n")
_headers, _, body = rest.partition("\r\n\r\n")
response_body = json.loads(body)

print("status line:", status_line)
print("response body:", response_body)
assert response_body == {"status": "ok", "prospect_id": 42, "audit_id": 99}, "unexpected response body"
mock_insert_prospect.assert_called_once_with(
    business_name="Test Biz", city="Lawrence", contact_email="owner@testbiz.example", source="website_form"
)
mock_generate_audit.assert_called_once_with(42, ["Test Biz"], {})
mock_send_email.assert_called_once_with("owner@testbiz.example", "Test Biz", "Fake audit summary.")
mock_update_status.assert_called_once_with(42, "sent")
mock_log.assert_called_once()

print("OK -- Formspree payload parsed correctly, correct functions called with correct args, clean 200 response")

"""Opt-in public, read-only synthetic demo. Local launcher stays unchanged."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit

from . import ui
from .domain import SourceLineage, TenantContext, ValidationError
from .review_storage import ReviewWorkflow
from .service import ingest
from .storage import Store
from .validation import FIELDS

DATABASE = ui.PARTICIPANT / "runtime" / "public-demo" / "demo.sqlite3"
TENANT = TenantContext("org_demo_alpha")
REVIEWER = "SYNTHETIC-DEMO-READ-ONLY"
LABEL = "SYNTHETIC / DEMONSTRATION DATA"
RECORDS = ("SYNTHETIC-DEMO-001", "SYNTHETIC-DEMO-002")


def port_from_env(env):
    value = env.get("PORT", "8000")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}", value) or not 1 <= int(value) <= 65535:
        raise ValidationError("PORT must be an integer from 1 to 65535")
    return int(value)


def demo_settings(env):
    origin = env.get("DEMO_PUBLIC_ORIGIN", "")
    try:
        parsed = urlsplit(origin)
        valid = (parsed.scheme == "https" and parsed.hostname and parsed.netloc == parsed.hostname
                 and re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", parsed.hostname)
                 and not parsed.path and not parsed.query and not parsed.fragment
                 and parsed.username is None and parsed.password is None)
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError("DEMO_PUBLIC_ORIGIN must be an HTTPS origin without path or port")
    return origin


def seed_demo(database):
    """Idempotent fixed synthetic captures; no photos, provider or fabricated observations."""
    database = Path(database).resolve()
    if not database.is_relative_to(ui.PARTICIPANT) or database.suffix != ".sqlite3":
        raise ValidationError("participant-local demo database required")
    database.parent.mkdir(parents=True, exist_ok=True)
    ids = set()
    with Store(database, TENANT) as store:
        workflow = ReviewWorkflow(store)
        if any(item["record_id"] not in RECORDS for item in workflow.queue()):
            raise ValidationError("demo database contains unrelated reviews")
        for number, record_id in enumerate(RECORDS, 1):
            row = dict.fromkeys(FIELDS, "")
            row.update(record_id=record_id, unit_id=record_id, org_id=TENANT.organization_id,
                       order_id="SYNTHETIC-NOT-A-REAL-ORDER", ordered_sku="UNKNOWN", ordered_asin="UNKNOWN",
                       operator_id="SYNTHETIC-DEMO-SEED", captured_at="2026-10-01T00:00:00Z")
            # Fixed date and identifiers describe the fixture, not a real capture.
            raw = json.dumps(row, sort_keys=True).encode()
            source = SourceLineage(LABEL, hashlib.sha256(raw).hexdigest(), number + 1)
            ingest(row, source, store)
            ids.add(workflow.route(record_id, record_id))
        if {item["review_id"] for item in workflow.queue()} != ids:
            raise ValidationError("demo database contains unexpected attempts")
    return frozenset(ids)


class DemoApplication(ui.UIApplication):
    def __init__(self, config, origin, review_ids):
        super().__init__(config)
        self.public_origin = origin
        self.public_host = urlsplit(origin).netloc
        self.review_ids = review_ids

    def _boundary(self, env):
        # TLS terminates at the hosting edge. Never trust forwarded identity/host headers.
        if env.get("HTTP_HOST") != self.public_host:
            raise ui.RequestError(403, "demo_host_required", "Use the configured demo origin.")
        if env.get("HTTP_ORIGIN") not in (None, self.public_origin):
            raise ui.RequestError(403, "cross_origin_denied", "Cross-origin requests are not permitted.")
        if env.get("HTTP_SEC_FETCH_SITE", "none") not in {"none", "same-origin"}:
            raise ui.RequestError(403, "cross_origin_denied", "Cross-origin requests are not permitted.")
        if env.get("REQUEST_METHOD") != "GET":
            raise ui.RequestError(405, "read_only_demo", "This demonstration is read-only.", (("Allow", "GET"),))

    def _dispatch(self, env):
        self._boundary(env)
        match = re.match(r"/api/reviews/([0-9]+)", env.get("PATH_INFO", ""))
        if match and int(match[1]) not in self.review_ids:
            raise ui.RequestError(404, "not_found", "Resource unavailable in this scope.")
        # Parent dispatch invokes this deployment boundary instead of the local boundary.
        mime, payload = super()._dispatch(env)
        path = env.get("PATH_INFO", "")
        if path == "/health":
            payload = {"status": "ok", "mode": "demo"}  # No provider-readiness claim.
        elif path == "/api/context":
            payload = {**payload, "environment": "restricted_demo", "read_only": True,
                       "demo_label": LABEL}
        elif path == "/api/reviews":
            payload = {**payload, "reviews": [r for r in payload["reviews"] if r["review_id"] in self.review_ids]}
        elif re.fullmatch(r"/api/reviews/[0-9]+", path):
            payload = {**payload, "allowed_transitions": []}
        return mime, payload


def create_demo_app(env):
    origin = demo_settings(env)
    port = port_from_env(env)
    # No environment-selected database, tenant, reviewer, images, collection or provider.
    config = ui.UIConfig(DATABASE, TENANT, REVIEWER, port, provider="disabled")
    ids = seed_demo(config.database)
    return DemoApplication(config, origin, ids)


def main(argv=None, *, environ=None):
    env = os.environ if environ is None else environ
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        mode = env.get("DEPLOYMENT_MODE", "local")
        port = port_from_env(env)
        if mode == "local":
            return ui.main(args + ([] if "--port" in args else ["--port", str(port)]))
        if mode != "demo" or args:
            raise ValidationError("demo mode accepts only server-controlled environment configuration")
        # Import before initializing any database; dependency errors must fail clearly.
        try:
            from waitress import serve
        except ImportError:
            raise ValidationError("install requirements-deploy.txt before demo startup") from None
        app = create_demo_app(env)
        serve(app, host="0.0.0.0", port=port, threads=4, channel_timeout=30,
              max_request_body_size=ui.MAX_BODY, max_request_header_size=8192,
              clear_untrusted_proxy_headers=True)
        return 0
    except (ValidationError, OSError, sqlite3.Error):
        print("Deployment startup rejected; check mode, PORT, demo origin configuration, dependencies and writable demo storage.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

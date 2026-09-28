"""Local, fixed-tenant WSGI adapter. Not authentication or an official wire schema."""

import argparse
from dataclasses import dataclass
from http import HTTPStatus
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from .domain import TenantContext, TenantMismatch, ValidationError, validate_unicode_scalars
from .review import HumanDecision, ReviewerContext, TRANSITIONS
from .review_storage import ReviewWorkflow
from .storage import ConflictError, Store


PARTICIPANT = Path(__file__).resolve().parents[2]
MAX_BODY = 65_536
NOTICE = "internal_ui_only_not_official_wire_contract"


@dataclass(frozen=True)
class UIConfig:
    database: Path
    tenant: TenantContext
    reviewer_id: str
    port: int = 8000

    def __post_init__(self):
        ReviewerContext(self.tenant, self.reviewer_id)
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValidationError("port must be between 1 and 65535")
        path = Path(self.database).resolve()
        if not path.is_relative_to(PARTICIPANT) or path.suffix != ".sqlite3":
            raise ValidationError("database must be a participant-local .sqlite3 file")
        object.__setattr__(self, "database", path)

    @property
    def authority(self):
        return f"127.0.0.1:{self.port}"

    @property
    def origin(self):
        return "http://" + self.authority


class RequestError(Exception):
    def __init__(self, status, code, message, headers=()):
        self.status, self.code, self.message, self.headers = status, code, message, headers


def _select(value, keys):
    return {key: value[key] for key in keys}


def queue_projection(item, events=()):
    transitions = [event for event in events if event["previous_state"] is not None
                   and event["previous_state"]["status"] != event["new_state"]["status"]]
    reopened = (item["status"] == "in_review" and bool(transitions)
                and transitions[-1]["previous_state"]["status"] == "reviewed")
    return {**_select(item, ("review_id", "record_id", "unit_id", "organization_id", "client_id",
                         "source_key", "status", "business_status", "revision", "created_at", "updated_at",
                         "uncertainty", "unresolved_decisions")), "reopened": reopened}


def detail_projection(item):
    """Select existing data without converting observations into business verdicts."""
    capture = item["capture"]
    return {
        **queue_projection(item), "format_notice": NOTICE,
        "capture": _select(capture, ("record_id", "tenant", "unit", "order", "reference",
                                     "operator_id", "captured_at", "source", "blockers")),
        **_select(item, ("evidence", "observations", "raw_response", "automated_assessment",
                        "human_decisions", "effective_results", "processing_error_at_routing")),
        "allowed_transitions": sorted(TRANSITIONS[item["status"]]),
    }


def history_projection(review_id, events):
    # (review_id, revision) is the existing event identity, not a fabricated ID.
    return {"review_id": review_id, "format_notice": NOTICE, "events": events}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _check_text(value):
    if isinstance(value, str):
        validate_unicode_scalars(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_text(key)
            _check_text(item)
    elif isinstance(value, list):
        for item in value:
            _check_text(item)


def _body(environ):
    if environ.get("HTTP_TRANSFER_ENCODING"):
        raise RequestError(400, "malformed_request", "Transfer encoding is unsupported.")
    if environ.get("CONTENT_TYPE", "").lower() not in {"application/json", "application/json; charset=utf-8"}:
        raise RequestError(415, "unsupported_media_type", "Use application/json with UTF-8.")
    size = environ.get("CONTENT_LENGTH", "")
    if not re.fullmatch(r"[0-9]{1,10}", size):
        raise RequestError(400, "malformed_request", "A valid Content-Length is required.")
    length = int(size)
    if length > MAX_BODY:
        raise RequestError(413, "body_too_large", "Request exceeds the 65536-byte limit.")
    try:
        raw = environ["wsgi.input"].read(length)
        if len(raw) != length:
            raise ValueError("incomplete body")
        def reject_constant(value):
            raise ValueError("non-finite number")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=reject_constant)
        _check_text(data)
        if type(data) is not dict:
            raise ValueError("object required")
    except (ValueError, RecursionError):
        raise RequestError(400, "malformed_request", "Body must be a valid UTF-8 JSON object.") from None
    return data


def _transition_arguments(data):
    required = {"status", "reason", "expected_revision", "command_id"}
    if not required.issubset(data) or set(data) - required - {"decisions"}:
        raise RequestError(400, "unsupported_fields", "Only documented transition fields are accepted.")
    if any(type(data[k]) is not str for k in ("status", "reason", "command_id")):
        raise ValidationError("transition text required")
    if type(data["expected_revision"]) is not int:
        raise ValidationError("integer revision required")
    decisions = data.get("decisions", [])
    if type(decisions) is not list or len(decisions) > 2:
        raise ValidationError("at most two decisions required")
    parsed = []
    for decision in decisions:
        if type(decision) is not dict or set(decision) != {"dimension", "verdict", "evidence_refs"}:
            raise ValidationError("unsupported decision fields")
        if type(decision["evidence_refs"]) is not list:
            raise ValidationError("evidence refs must be a list")
        parsed.append(HumanDecision(decision["dimension"], decision["verdict"], tuple(decision["evidence_refs"])))
    return {**{key: data[key] for key in required}, "decisions": tuple(parsed)}


class UIApplication:
    def __init__(self, config: UIConfig):
        self.config = config
        self.reviewer = ReviewerContext(config.tenant, config.reviewer_id)
        # Fixed mapping, read once. Request paths never become filesystem paths.
        static = Path(__file__).parent / "ui_static"
        self.assets = {route: (mime, (static / filename).read_bytes()) for route, mime, filename in (
            ("/", "text/html; charset=utf-8", "index.html"),
            ("/assets/workstation.css", "text/css; charset=utf-8", "workstation.css"),
            ("/assets/workstation.js", "text/javascript; charset=utf-8", "workstation.js"),
        )}

    def _boundary(self, env):
        if (env.get("REMOTE_ADDR") != "127.0.0.1" or env.get("HTTP_HOST") != self.config.authority
                or env.get("wsgi.url_scheme") != "http"):
            raise RequestError(403, "local_origin_required", "Use the configured loopback origin.")
        origin = env.get("HTTP_ORIGIN")
        if origin is not None and origin != self.config.origin:
            raise RequestError(403, "cross_origin_denied", "Cross-origin requests are not permitted.")
        if env.get("HTTP_SEC_FETCH_SITE", "none") not in {"same-origin", "none"}:
            raise RequestError(403, "cross_origin_denied", "Cross-origin requests are not permitted.")
        if env["REQUEST_METHOD"] == "POST" and (
            origin != self.config.origin or env.get("HTTP_X_RETURNS_REQUEST") != "1"
        ):
            raise RequestError(403, "mutation_origin_required", "Same-origin mutation headers are required.")

    def _dispatch(self, env):
        self._boundary(env)
        path, method = env.get("PATH_INFO", ""), env["REQUEST_METHOD"]
        match = re.fullmatch(r"/api/reviews/([1-9][0-9]{0,18})(/history|/transition)?", path)
        if path not in self.assets and path not in {"/health", "/api/context", "/api/reviews"} and match is None:
            raise RequestError(404, "not_found", "Resource unavailable in this scope.")
        allowed = "POST" if match and match[2] == "/transition" else "GET"
        if method != allowed:
            raise RequestError(405, "method_not_allowed", "Method not supported.", (("Allow", allowed),))
        try:
            query_text = env.get("QUERY_STRING", "")
            if len(query_text) > 1024:
                raise ValueError("query too long")
            query = parse_qs(query_text, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            if (set(query) - ({"status"} if path == "/api/reviews" else set())
                    or any(len(v) != 1 for v in query.values())):
                raise ValueError("unsupported query")
        except ValueError:
            raise RequestError(400, "unsupported_query", "Only a single queue status filter is supported.") from None
        if path in self.assets:
            return self.assets[path]
        if path == "/health":
            return "application/json", {"status": "ok"}
        if path == "/api/context":
            return "application/json", {"organization_id": self.config.tenant.organization_id,
                "client_id": self.config.tenant.client_id, "reviewer_id": self.config.reviewer_id,
                "environment": "local_demo", "format_notice": NOTICE}
        arguments = _transition_arguments(_body(env)) if method == "POST" else None
        # Connections live only for one request. No adapter SQL or browser-selected scope.
        with Store(self.config.database, self.config.tenant) as store:
            workflow = ReviewWorkflow(store)
            if path == "/api/reviews":
                return "application/json", {"format_notice": NOTICE, "reviews": [queue_projection(item,
                    workflow.history(item["review_id"], item["record_id"], item["unit_id"]))
                    for item in workflow.queue(status=query.get("status", [None])[0])]}
            review_id = int(match[1])
            if review_id > 2**63 - 1:
                raise TenantMismatch("unavailable review")
            # Public queue API resolves record/unit association within the trusted scope.
            # Deliberately O(n) for the small local dataset; no unscoped SQL shortcut.
            item = next((i for i in workflow.queue() if i["review_id"] == review_id), None)
            if item is None:
                raise TenantMismatch("unavailable review")
            record_id, unit_id = item["record_id"], item["unit_id"]
            if match[2] == "/history":
                payload = history_projection(review_id, workflow.history(review_id, record_id, unit_id))
            elif match[2] == "/transition":
                event = workflow.transition(review_id, record_id, unit_id, reviewer=self.reviewer, **arguments)
                payload = {"format_notice": NOTICE, "review_id": review_id, "event": event}
            else:
                payload = detail_projection(workflow.get(review_id, record_id, unit_id))
            return "application/json", payload

    def __call__(self, environ, start_response):
        status, extra_headers = 200, ()
        try:
            content_type, payload = self._dispatch(environ)
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("utf-8")
        except Exception as exc:
            if isinstance(exc, RequestError):
                status, code, message, extra_headers = exc.status, exc.code, exc.message, exc.headers
            elif isinstance(exc, TenantMismatch):
                status, code, message = 404, "not_found", "Resource unavailable in this scope."
            elif isinstance(exc, ConflictError):
                status, code, message = 409, "review_conflict", "Stale revision or command conflict; reload before a new action."
            elif isinstance(exc, ValidationError):
                status, code, message = 422, "validation_failed", "Request violates the existing review contract."
            else:
                status, code, message = 500, "internal_error", "The request could not be completed."
            content_type = "application/json"
            body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
        headers = [("Content-Type", content_type), ("Content-Length", str(len(body))),
                   ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                   ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
                   ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
                   ("Cross-Origin-Resource-Policy", "same-origin"), *extra_headers]
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [body]


def create_app(config: UIConfig):
    """Explicit startup initializes schemas only; never imports or routes captures."""
    app = UIApplication(config)
    config.database.parent.mkdir(parents=True, exist_ok=True)
    with Store(config.database, config.tenant) as store:
        ReviewWorkflow(store)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--reviewer", required=True, help="Actual trusted local reviewer identity; no default")
    parser.add_argument("--client", default=None, help="Real trusted client context only; otherwise null")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=PARTICIPANT / "runtime" / "returns.sqlite3")
    args = parser.parse_args(argv)
    try:
        config = UIConfig(args.database, TenantContext(args.organization, args.client), args.reviewer, args.port)
        app = create_app(config)
        with make_server("127.0.0.1", config.port, app) as server:
            print(f"Local Returns Manager adapter: {config.origin} (not production authentication)", flush=True)
            server.serve_forever()
        return 0
    except (ValidationError, OSError, sqlite3.Error) as exc:
        print(f"UI startup failed ({type(exc).__name__}); check reviewer, organization, port and database configuration.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

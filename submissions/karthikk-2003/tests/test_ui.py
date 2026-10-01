"""Local adapter tests; source rows and injected observations are TEST fixtures only."""

from dataclasses import asdict, replace
from contextlib import closing, redirect_stderr
import http.client
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler
from wsgiref.util import setup_testing_defaults

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))

from returns_manager.domain import TenantContext, ValidationError
from returns_manager.review_storage import ReviewWorkflow
from returns_manager.service import ingest, inspect_capture
from returns_manager.storage import Store
from returns_manager.validation import read_csv, parse_record
from returns_manager.vision import FixtureProvider, ImageInput, ObservationScope
from returns_manager import ui


class UITests(unittest.TestCase):
    def setUp(self):
        scratch = PARTICIPANT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "ui-test.sqlite3"
        self.alpha, self.bravo = TenantContext("org_demo_alpha"), TenantContext("org_demo_bravo")
        self.row, self.source = next((r, s) for r, s in read_csv(PARTICIPANT.parents[1] / "data/returns_sample.csv")
                                     if r["org_id"] == self.alpha.organization_id)
        self.config = ui.UIConfig(self.database, self.alpha, "TEST-configured-reviewer")
        self.app = ui.create_app(self.config)
        self.ids = {}
        for tenant in (self.alpha, self.bravo):
            # Deliberately identical record/unit IDs in two existing orgs; TEST isolation probe.
            row = {**self.row, "org_id": tenant.organization_id}
            with Store(self.database, tenant) as store:
                ingest(row, self.source, store)
                workflow = ReviewWorkflow(store)
                self.ids[tenant.organization_id] = workflow.route(row["record_id"], row["unit_id"])
        self.review = self.ids[self.alpha.organization_id]
        self.foreign = self.ids[self.bravo.organization_id]
        self.url = f"/api/reviews/{self.review}"

    def request(self, path="/health", method="GET", data=None, raw=None, overrides=None, app=None):
        env = {}
        setup_testing_defaults(env)
        path, _, query = path.partition("?")
        payload = raw if raw is not None else (json.dumps(data).encode() if data is not None else b"")
        env.update({"PATH_INFO": path, "QUERY_STRING": query, "REQUEST_METHOD": method,
                    "HTTP_HOST": self.config.authority, "REMOTE_ADDR": "127.0.0.1",
                    "wsgi.input": io.BytesIO(payload), "CONTENT_LENGTH": str(len(payload)),
                    "CONTENT_TYPE": "application/json"})
        if method == "POST":
            env.update(HTTP_ORIGIN=self.config.origin, HTTP_X_RETURNS_REQUEST="1", HTTP_SEC_FETCH_SITE="same-origin")
        for key, value in (overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = {}
        def start_response(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        body = b"".join((app or self.app)(env, start_response))
        result["body"] = body
        result["json"] = json.loads(body) if result["headers"]["Content-Type"] == "application/json" else None
        return result

    def command(self, **changes):
        return {"status": "in_review", "reason": "TEST explicit review", "expected_revision": 1,
                "command_id": "TEST-command-1", **changes}

    def transition(self, **changes):
        return self.request(self.url + "/transition", "POST", self.command(**changes))

    def history(self, tenant=None, review=None):
        with Store(self.database, tenant or self.alpha) as store:
            return ReviewWorkflow(store).history(review or self.review, self.row["record_id"], self.row["unit_id"])

    def test_health_and_minimal_shell_have_safe_headers(self):
        result = self.request()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"], {"status": "ok"})
        self.assertEqual(result["headers"]["Cache-Control"], "no-store")
        self.assertEqual(result["headers"]["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", result["headers"]["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", result["headers"])
        shell = self.request("/")
        self.assertEqual(shell["status"], 200)
        self.assertIn(b"not implemented yet", shell["body"])
        self.assertNotIn(str(self.database).encode(), shell["body"])

    def test_empty_collection_source_cli_rejected_before_server_start(self):
        for value in ("", "   "):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), patch.object(ui, "create_app") as create:
                with self.assertRaises(SystemExit) as error:
                    ui.main(["--organization", "org_demo_alpha", "--reviewer", "TEST-reviewer",
                             "--collection-source", value])
                self.assertEqual(error.exception.code, 2)
                create.assert_not_called()

    def test_workstation_context_is_trusted_and_read_only(self):
        result = self.request("/api/context")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"]["reviewer_id"], self.config.reviewer_id)
        self.assertEqual(result["json"]["organization_id"], self.alpha.organization_id)
        self.assertIsNone(result["json"]["client_id"])
        self.assertEqual(result["json"]["environment"], "local_demo")
        self.assertNotIn(str(self.database).encode(), result["body"])
        self.assertEqual(self.request("/api/context?reviewer_id=TEST-forged")["status"], 400)
        self.assertEqual(self.request("/api/context", "POST", {})["status"], 405)
        self.assertEqual(len(self.history()), 1)

    def test_workstation_assets_are_fixed_allowlist_with_restrictive_csp(self):
        for path, mime in (("/assets/workstation.js", "text/javascript; charset=utf-8"),
                           ("/assets/workstation.css", "text/css; charset=utf-8")):
            with self.subTest(path=path):
                result = self.request(path)
                self.assertEqual(result["status"], 200)
                self.assertEqual(result["headers"]["Content-Type"], mime)
                self.assertTrue(result["body"])
                csp = result["headers"]["Content-Security-Policy"]
                self.assertIn("script-src 'self'", csp)
                self.assertIn("connect-src 'self'", csp)
                self.assertNotIn("unsafe-inline", csp)
                self.assertNotIn("unsafe-eval", csp)
        for path in ("/assets/ui.py", "/assets/../ui.py", "/assets/%2e%2e/ui.py", "/assets/", "/assets/results.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 404)

    def test_reopened_queue_label_comes_from_real_history_not_new_status(self):
        def current():
            return self.request("/api/reviews")["json"]["reviews"][0]
        self.assertFalse(current()["reopened"])
        self.transition()
        self.assertFalse(current()["reopened"])
        self.transition(status="reviewed", expected_revision=2, command_id="TEST-finish")
        self.transition(status="in_review", expected_revision=3, command_id="TEST-reopen")
        self.assertTrue(current()["reopened"])
        self.assertEqual(current()["status"], "in_review")
        self.assertEqual(current()["business_status"], "pending_review")
        self.transition(status="in_review", expected_revision=4, command_id="TEST-note")
        self.assertTrue(current()["reopened"])
        self.transition(status="pending_review", expected_revision=5, command_id="TEST-pending")
        self.transition(status="in_review", expected_revision=6, command_id="TEST-restart")
        self.assertFalse(current()["reopened"])

    def test_reopened_queue_history_stays_tenant_scoped(self):
        self.transition()
        self.transition(status="reviewed", expected_revision=2, command_id="TEST-finish")
        self.transition(status="in_review", expected_revision=3, command_id="TEST-reopen")
        app = ui.create_app(replace(self.config, tenant=self.bravo))
        rows = self.request("/api/reviews", app=app)["json"]["reviews"]
        self.assertEqual([r["review_id"] for r in rows], [self.foreign])
        self.assertFalse(rows[0]["reopened"])
        self.assertEqual(self.request(self.url + "/history", app=app)["status"], 404)

    def test_context_and_assets_do_not_route_or_append_history(self):
        before = self.history()
        for _ in range(2):
            for path in ("/api/context", "/assets/workstation.js", "/assets/workstation.css", "/api/reviews"):
                self.assertEqual(self.request(path)["status"], 200)
        self.assertEqual(self.history(), before)

    def test_queue_scope_filter_and_minimal_projection(self):
        result = self.request("/api/reviews")["json"]["reviews"]
        self.assertEqual([i["review_id"] for i in result], [self.review])
        self.assertEqual(result[0]["organization_id"], self.alpha.organization_id)
        self.assertIsNone(result[0]["client_id"])
        self.assertNotIn("capture", result[0])
        self.assertNotIn("raw_response", result[0])
        self.assertEqual(self.request("/api/reviews?status=in_review")["json"]["reviews"], [])
        self.assertEqual(self.request("/api/reviews?status=TEST-bad")["status"], 422)

    def test_detail_preserves_source_and_four_separate_results(self):
        result = self.request(self.url)
        self.assertEqual(result["status"], 200)
        detail = result["json"]
        self.assertEqual(detail["capture"]["source"], asdict(self.source))
        self.assertEqual(detail["capture"]["order"]["ordered_sku"], self.row["ordered_sku"])
        self.assertEqual(detail["record_id"], self.row["record_id"])
        self.assertEqual(detail["unit_id"], self.row["unit_id"])
        self.assertEqual([e["reference"] for e in detail["evidence"]], self.row["photo_refs"].split(";"))
        self.assertTrue(all(e["availability"] == "missing" for e in detail["evidence"]))
        self.assertIsNone(detail["observations"])
        self.assertIsNone(detail["raw_response"])
        self.assertIsNone(detail["automated_assessment"]["condition"]["grade"])
        self.assertEqual(detail["automated_assessment"]["completeness"]["missing_components"], [])
        self.assertEqual(detail["business_status"], "pending_review")
        self.assertEqual(detail["allowed_transitions"], ["in_review"])
        self.assertNotIn("raw_fields", detail["capture"])

    def test_history_keeps_system_actor_revision_and_provenance(self):
        result = self.request(self.url + "/history")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"]["events"], self.history())
        event = result["json"]["events"][0]
        self.assertEqual(event["revision"], 1)
        self.assertEqual(event["actor_kind"], "system")
        self.assertTrue(event["timestamp"])

    def test_cross_tenant_detail_history_and_mutation_are_unavailable(self):
        before = self.history(self.bravo, self.foreign)
        for suffix, method in (("", "GET"), ("/history", "GET"), ("/transition", "POST")):
            with self.subTest(suffix=suffix):
                foreign = self.request(f"/api/reviews/{self.foreign}" + suffix, method, self.command() if method == "POST" else None)
                absent = self.request("/api/reviews/999999" + suffix, method, self.command() if method == "POST" else None)
                self.assertEqual(foreign["status"], 404)
                self.assertEqual(foreign["body"], absent["body"])
        self.assertEqual(self.history(self.bravo, self.foreign), before)

    def test_record_unit_association_is_revalidated(self):
        with Store(self.database, self.alpha) as store:
            item = ReviewWorkflow(store).get(self.review, self.row["record_id"], self.row["unit_id"])
        for key in ("record_id", "unit_id"):
            with self.subTest(key=key), patch.object(ReviewWorkflow, "queue", return_value=[{**item, key: "TEST-wrong"}]):
                self.assertEqual(self.request(self.url)["status"], 404)
                self.assertEqual(self.request(self.url + "/history")["status"], 404)
                self.assertEqual(self.transition()["status"], 404)

    def test_browser_scope_and_reviewer_fields_are_rejected(self):
        for field, value in (("organization_id", self.bravo.organization_id), ("org_id", self.bravo.organization_id),
                             ("client_id", "TEST-forged"), ("reviewer_id", "TEST-forged"),
                             ("record_id", "TEST-forged"), ("unit_id", "TEST-forged")):
            with self.subTest(field=field):
                self.assertEqual(self.transition(**{field: value})["status"], 400)
                self.assertEqual(self.request(self.url + "?" + field + "=TEST-forged")["status"], 400)
        self.assertEqual(len(self.history()), 1)

    def test_configured_reviewer_is_attributed_despite_forged_headers(self):
        result = self.request(self.url + "/transition", "POST", self.command(), overrides={
            "HTTP_X_REVIEWER_ID": "TEST-forged", "HTTP_X_ORGANIZATION_ID": self.bravo.organization_id})
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"]["event"]["actor_id"], self.config.reviewer_id)
        self.assertEqual(result["json"]["event"]["actor_kind"], "human")

    def test_invalid_transition_and_validation_are_rejected(self):
        for changes in ({"status": "reviewed"}, {"status": "restock"}, {"reason": ""},
                        {"expected_revision": True}, {"expected_revision": 0}, {"reason": []},
                        {"command_id": "system:route"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.transition(**changes)["status"], 422)
        self.assertEqual(len(self.history()), 1)

    def test_stale_revision_and_command_reuse_conflict(self):
        self.assertEqual(self.transition()["status"], 200)
        self.assertEqual(self.transition(command_id="TEST-stale")["status"], 409)
        self.assertEqual(self.transition(reason="TEST-changed")["status"], 409)
        self.assertEqual(len(self.history()), 2)

    def test_assertions_require_preexisting_active_review_for_both_dimensions(self):
        before = self.request(self.url)["json"]
        initial_history = self.history()
        for dimension in ("identity", "completeness"):
            with self.subTest(dimension=dimension):
                decision = {"dimension": dimension, "verdict": "UNCERTAIN", "evidence_refs": []}
                self.assertEqual(self.transition(decisions=[decision])["status"], 422)
                self.assertEqual(self.history(), initial_history)
        self.assertEqual(self.transition()["status"], 200)
        for revision, dimension in enumerate(("identity", "completeness"), 2):
            decision = {"dimension": dimension, "verdict": "UNCERTAIN", "evidence_refs": []}
            self.assertEqual(self.transition(expected_revision=revision, command_id="TEST-active-" + dimension,
                                             decisions=[decision])["status"], 200)
        after = self.request(self.url)["json"]
        self.assertEqual(set(after["human_decisions"]), {"identity", "completeness"})
        for key in ("capture", "evidence", "raw_response", "observations", "automated_assessment", "uncertainty"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.history()[:1], initial_history)
        self.assertEqual(len(self.history()), 4)
        self.assertEqual(self.transition(command_id="TEST-old-revision")["status"], 409)
        self.assertEqual(len(self.history()), 4)

    def test_idempotent_retry_keeps_same_event_and_history(self):
        first = self.transition()
        self.assertEqual(first["status"], 200)
        self.assertEqual(self.transition()["json"], first["json"])
        history = self.request(self.url + "/history")["json"]["events"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1], first["json"]["event"])

    def test_uncertain_human_review_keeps_original_evidence_and_pending_business_status(self):
        before = self.request(self.url)["json"]
        self.transition()
        result = self.transition(status="reviewed", expected_revision=2, command_id="TEST-reviewed",
            decisions=[{"dimension": "identity", "verdict": "UNCERTAIN", "evidence_refs": []}])
        self.assertEqual(result["status"], 200)
        after = self.request(self.url)["json"]
        self.assertEqual(after["status"], "reviewed")
        self.assertEqual(after["business_status"], "pending_review")
        for key in ("capture", "evidence", "raw_response", "observations", "automated_assessment"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["effective_results"]["identity"]["source"], "human")
        self.assertEqual(after["human_decisions"]["identity"]["reviewer_id"], self.config.reviewer_id)

    def test_unsupported_grade_disposition_and_unavailable_citations_rejected(self):
        self.transition()
        for dimension, verdict, refs in (("condition", "PASS", []), ("disposition", "restock", []),
                                          ("identity", "PASS", []), ("completeness", "FAIL", ["TEST-unknown-evidence"])):
            with self.subTest(dimension=dimension, verdict=verdict):
                result = self.transition(expected_revision=2, command_id="TEST-reject", decisions=[
                    {"dimension": dimension, "verdict": verdict, "evidence_refs": refs}])
                self.assertEqual(result["status"], 422)
        self.assertEqual(len(self.history()), 2)

    def test_get_requests_do_not_create_review_events(self):
        before = self.history()
        for _ in range(2):
            for path in ("/", "/health", "/api/reviews", self.url, self.url + "/history"):
                self.assertEqual(self.request(path)["status"], 200)
        self.assertEqual(self.history(), before)
        with Store(self.database, self.alpha) as store:
            self.assertEqual(len(ReviewWorkflow(store).queue()), 1)
            self.assertEqual(store.vision_attempts(self.row["record_id"]), [])

    def test_empty_database_is_not_implicitly_seeded(self):
        app = ui.create_app(replace(self.config, database=Path(self.tmp.name) / "empty.sqlite3"))
        self.assertEqual(self.request("/api/reviews", app=app)["json"]["reviews"], [])
        self.assertEqual(self.request(self.url, app=app)["status"], 404)

    def test_malformed_json_duplicate_keys_and_invalid_unicode_rejected(self):
        bodies = (b"{", b"[]", b"null", b' {"status":"a","status":"b"}', b'{"x":NaN}',
                  b' {"x":"\\ud800"}', b' {"x":"\xff"}', b"[" * 2000)
        for raw in bodies:
            with self.subTest(raw=raw[:30]):
                self.assertEqual(self.request(self.url + "/transition", "POST", raw=raw)["status"], 400)
        self.assertEqual(self.request(self.url + "/transition", "POST", data={})["status"], 400)
        self.assertEqual(len(self.history()), 1)

    def test_body_framing_size_and_media_type_enforced(self):
        for headers, expected in (({"CONTENT_LENGTH": None}, 400), ({"CONTENT_LENGTH": "-1"}, 400),
                                  ({"CONTENT_LENGTH": "65537"}, 413), ({"CONTENT_LENGTH": "500"}, 400),
                                  ({"HTTP_TRANSFER_ENCODING": "chunked"}, 400), ({"CONTENT_TYPE": "text/plain"}, 415)):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(self.url + "/transition", "POST", self.command(), overrides=headers)["status"], expected)

    def test_unsupported_methods_do_not_mutate(self):
        for path, method in (("/health", "POST"), (self.url, "DELETE"), (self.url, "PUT"),
                             (self.url, "HEAD"), (self.url + "/transition", "GET"), (self.url, "OPTIONS")):
            with self.subTest(path=path, method=method):
                result = self.request(path, method)
                self.assertEqual(result["status"], 405)
                self.assertIn("Allow", result["headers"])
        self.assertEqual(len(self.history()), 1)

    def test_origin_host_and_remote_boundaries(self):
        for headers in ({"HTTP_HOST": "attacker.invalid:8000"}, {"REMOTE_ADDR": "192.0.2.1"},
                        {"HTTP_ORIGIN": "http://attacker.invalid"}, {"HTTP_ORIGIN": "null"},
                        {"HTTP_SEC_FETCH_SITE": "cross-site"}, {"HTTP_SEC_FETCH_SITE": "same-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/reviews", overrides=headers)["status"], 403)

    def test_mutations_require_origin_and_non_simple_header(self):
        for headers in ({"HTTP_ORIGIN": None}, {"HTTP_X_RETURNS_REQUEST": None},
                        {"HTTP_X_RETURNS_REQUEST": "0"}, {"HTTP_ORIGIN": "http://127.0.0.1:9999"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(self.url + "/transition", "POST", self.command(), overrides=headers)["status"], 403)
        self.assertEqual(len(self.history()), 1)

    def test_no_filesystem_routes_or_traversal(self):
        for path in ("/../data/returns_sample.csv", "/%2e%2e/data/returns_sample.csv", "/C:/Windows/win.ini",
                     "/static/../../agent/returns_manager/ui.py", "/ui.py", "/returns.sqlite3", "/data/returns_sample.csv",
                     "/evaluation/results.json", "/.git/config", "/\\..\\README.md", "//health"):
            with self.subTest(path=path):
                result = self.request(path)
                self.assertEqual(result["status"], 404)
                self.assertNotIn(str(self.database).encode(), result["body"])

    def test_query_fields_duplicates_and_invalid_ids_are_rejected(self):
        for path in ("/api/reviews?status=a&status=b", "/api/reviews?organization_id=org_demo_bravo",
                     "/api/reviews?status", self.url + "?record_id=TEST-other", "/health?x=y"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 400)
        for identifier in ("0", "-1", "01", "9223372036854775808", "1%2fhistory", "x"):
            with self.subTest(identifier=identifier):
                self.assertEqual(self.request("/api/reviews/" + identifier)["status"], 404)

    def test_unexpected_errors_are_generic_json_not_success(self):
        with patch.object(ReviewWorkflow, "queue", side_effect=RuntimeError("TEST secret C:/private/db.sqlite3 traceback")):
            result = self.request("/api/reviews")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["json"]["error"]["code"], "internal_error")
        self.assertNotIn(b"private", result["body"])
        self.assertNotIn(b"traceback", result["body"])

    def test_transaction_failure_rolls_back_and_retry_succeeds(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("CREATE TRIGGER TEST_fail BEFORE INSERT ON review_events BEGIN SELECT RAISE(ABORT, 'TEST fault'); END")
        self.assertEqual(self.transition()["status"], 500)
        self.assertEqual(len(self.history()), 1)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("DROP TRIGGER TEST_fail")
        self.assertEqual(self.transition()["status"], 200)
        self.assertEqual(len(self.history()), 2)

    def test_untrusted_text_remains_json_data(self):
        reason = '<script>alert("TEST")</script>'
        result = self.transition(reason=reason)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["headers"]["Content-Type"], "application/json")
        self.assertEqual(result["json"]["event"]["reason"], reason)
        self.assertIn("default-src 'none'", result["headers"]["Content-Security-Policy"])
        self.assertNotIn(reason.encode(), self.request("/")["body"])

    def test_validated_fixture_conflicts_and_visibility_preserved(self):
        capture = parse_record(self.row, self.alpha, self.source)
        scope = ObservationScope.from_capture(capture)
        images = tuple(ImageInput(scope, f"TEST-image-{i}", f"TEST-evidence-{i}", image.reference,
                                   "returned_product", "fixture") for i, image in enumerate(capture.images))
        payload = {"scope": asdict(scope), "identity": [
            {"field": "model", "state": "observed", "values": [value], "evidence_refs": [f"TEST-evidence-{i}"],
             "limitations": ["TEST fixture only"]} for i, value in enumerate(("TEST-A", "TEST-B"))],
            "components": [{"component": "TEST-cable", "presence": "unknown", "visibility": "occluded", "quantity": None,
                            "quantity_reliable": False, "absence_basis": None, "evidence_refs": ["TEST-evidence-0"],
                            "limitations": ["TEST obscured"]}], "condition": [], "limitations": ["TEST no images"]}
        with Store(self.database, self.alpha) as store:
            attempt = inspect_capture(self.row, self.source, store, images, FixtureProvider(json.dumps(payload)))
            review = ReviewWorkflow(store).route(self.row["record_id"], self.row["unit_id"], attempt_id=attempt)
            stored = ReviewWorkflow(store).get(review, self.row["record_id"], self.row["unit_id"])
        detail = self.request(f"/api/reviews/{review}")["json"]
        self.assertEqual(detail["observations"], stored["observations"])
        self.assertEqual(detail["raw_response"], stored["raw_response"])
        self.assertTrue(detail["observations"]["conflicts"])
        self.assertEqual(detail["observations"]["components"][0]["presence"], "unknown")
        self.assertEqual(detail["observations"]["components"][0]["visibility"], "occluded")
        self.assertEqual(detail["automated_assessment"]["completeness"]["missing_components"], [])
        self.assertTrue(all(i["availability"] == "fixture_only" for i in detail["evidence"]))

    def test_configuration_requires_reviewer_and_participant_database(self):
        for change in ({"reviewer_id": ""}, {"reviewer_id": "\ud800"}, {"port": 0}, {"port": True},
                       {"database": PARTICIPANT / "README.md"}, {"database": PARTICIPANT.parents[1] / "TEST.sqlite3"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                replace(self.config, **change)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            ui.main(["--organization", self.alpha.organization_id])
        self.assertEqual(error.exception.code, 2)

    def test_null_client_scope_is_not_wildcard(self):
        # No invented client ID: use only the existing null scope and verify exact construction.
        self.assertIsNone(self.config.tenant.client_id)
        with Store(self.database, self.alpha) as store:
            self.assertEqual(store._scope, (self.alpha.organization_id, "null"))
        self.assertTrue(all(r["client_id"] is None for r in self.request("/api/reviews")["json"]["reviews"]))

    def test_real_loopback_http_smoke_all_endpoints(self):
        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *args):
                pass
        server = make_server("127.0.0.1", 0, self.app, handler_class=QuietHandler)
        config = replace(self.config, port=server.server_port)
        server.set_app(ui.create_app(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ("/", "/health", "/api/reviews", self.url, self.url + "/history"):
                with self.subTest(path=path):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read())
                    finally:
                        connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("POST", self.url + "/transition", json.dumps(self.command()), headers={
                    "Content-Type": "application/json", "Origin": config.origin, "X-Returns-Request": "1"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["event"]["actor_id"], self.config.reviewer_id)
            finally:
                connection.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()

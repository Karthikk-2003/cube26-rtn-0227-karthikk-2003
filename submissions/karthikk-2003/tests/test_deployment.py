"""Offline deployment checks. All credentials/context here are synthetic test data."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from wsgiref.util import setup_testing_defaults

PARTICIPANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARTICIPANT / "agent"))
from returns_manager import deployment as dep, ui
from returns_manager.domain import ValidationError, TenantContext
from returns_manager.storage import Store
from returns_manager.review_storage import ReviewWorkflow


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        scratch = PARTICIPANT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "demo.sqlite3"
        self.token = "TEST_ONLY_NOT_A_SECRET_1234567890123456"
        self.env = {"DEPLOYMENT_MODE": "demo", "DEMO_PUBLIC_ORIGIN": "https://demo.example.test",
                    "DEMO_ACCESS_TOKEN": self.token, "PORT": "9123"}
        self.patch = patch.object(dep, "DATABASE", self.database)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.app = dep.create_demo_app(self.env)

    def request(self, path="/api/context", method="GET", auth=True, **overrides):
        env = {}
        setup_testing_defaults(env)
        path, _, query = path.partition("?")
        env.update(PATH_INFO=path, QUERY_STRING=query, REQUEST_METHOD=method,
                   HTTP_HOST="demo.example.test", REMOTE_ADDR="192.0.2.1",
                   CONTENT_LENGTH="0", **{"wsgi.input": io.BytesIO(b"")})
        if auth:
            env["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(("demo:" + self.token).encode()).decode()
        env.update(overrides)
        result = {}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        result["body"] = b"".join(self.app(env, start))
        if result["headers"]["Content-Type"] == "application/json":
            result["json"] = json.loads(result["body"])
        return result

    def test_port_default_and_bounds(self):
        self.assertEqual(dep.port_from_env({}), 8000)
        self.assertEqual(dep.port_from_env({"PORT": "12345"}), 12345)
        for value in ("0", "65536", "-1", "abc", "", "8000.0", " 8000"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                dep.port_from_env({"PORT": value})

    def test_configuration_requires_https_and_strong_access_configuration(self):
        for origin in ("", "http://demo.example.test", "https://user:pass@demo.example.test",
                       "https://demo.example.test/path", "https://demo.example.test?x=1",
                       "https://demo.example.test:443", "https://demo.example.test/"):
            with self.subTest(origin=origin), self.assertRaises(ValidationError):
                dep.demo_settings({**self.env, "DEMO_PUBLIC_ORIGIN": origin})
        for token in ("", "short", "x" * 129, "x" * 32 + "\n"):
            with self.subTest(length=len(token)), self.assertRaises(ValidationError):
                dep.demo_settings({**self.env, "DEMO_ACCESS_TOKEN": token})

    def test_unauthorized_requests_rejected_without_content(self):
        for path in ("/", "/assets/workstation.js", "/api/context", "/api/reviews"):
            with self.subTest(path=path):
                result = self.request(path, auth=False)
                self.assertEqual(result["status"], 401)
                self.assertIn("WWW-Authenticate", result["headers"])
                self.assertNotIn(b"SYNTHETIC-DEMO-001", result["body"])
        for header in ("Basic !", "Bearer TEST", "Basic " + "A" * 600,
                       "Basic " + base64.b64encode(b"demo:wrong").decode()):
            self.assertEqual(self.request(HTTP_AUTHORIZATION=header)["status"], 401)

    def test_host_origin_and_forwarded_headers_cannot_bypass_access(self):
        self.assertEqual(self.request(HTTP_HOST="attacker.example")["status"], 403)
        self.assertEqual(self.request(HTTP_ORIGIN="https://attacker.example")["status"], 403)
        self.assertEqual(self.request(HTTP_SEC_FETCH_SITE="cross-site")["status"], 403)
        self.assertEqual(self.request(auth=False, HTTP_X_FORWARDED_USER="demo",
                         HTTP_X_FORWARDED_HOST="demo.example.test")["status"], 401)
        self.assertEqual(self.request(HTTP_HOST="wrong", HTTP_X_FORWARDED_HOST="demo.example.test")["status"], 403)

    def test_health_is_minimal_and_public_without_provider_claim(self):
        result = self.request("/health", auth=False)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["json"], {"status": "ok", "mode": "demo"})
        self.assertNotIn(self.token.encode(), result["body"])

    def test_context_is_fixed_read_only_and_has_no_credentials(self):
        result = self.request()
        self.assertEqual(result["status"], 200)
        self.assertTrue(result["json"]["read_only"])
        self.assertEqual(result["json"]["ai_provider"], "disabled")
        self.assertFalse(result["json"]["demo_enabled"])
        self.assertFalse(result["json"]["collection_enabled"])
        self.assertEqual(result["json"]["organization_id"], "org_demo_alpha")
        self.assertIsNone(result["json"]["client_id"])
        self.assertNotIn(self.token.encode(), result["body"])
        self.assertNotIn(b"GROQ_API_KEY", result["body"])
        self.assertNotIn(str(self.database).encode(), result["body"])

    def test_all_mutations_blocked_even_with_access(self):
        review = min(self.app.review_ids)
        for path in ("/api/demo/inspect", f"/api/reviews/{review}/transition", "/health"):
            self.assertEqual(self.request(path, method="POST")["status"], 405)
            self.assertEqual(self.request(path, method="POST", auth=False)["status"], 401)

    def test_remote_tenant_paths_and_provider_selection_rejected(self):
        for query in ("organization_id=org_demo_bravo", "database=other.sqlite3",
                      "collection_source=../../", "provider=groq", "reviewer_id=other"):
            self.assertEqual(self.request("/api/reviews?" + query)["status"], 400)
        for path in ("/../../.env", "/runtime/real-products.sqlite3", "/collection/image.jpg",
                     "/assets/../deployment.py", "/api/reviews/99999"):
            self.assertEqual(self.request(path)["status"], 404)

    def test_seed_is_idempotent_and_has_no_photographs_or_observations(self):
        before = self.request("/api/reviews")["json"]
        ids = dep.seed_demo(self.database)
        self.assertEqual(ids, self.app.review_ids)
        self.assertEqual(self.request("/api/reviews")["json"], before)
        self.assertEqual(len(before["reviews"]), 2)
        for review in ids:
            detail = self.request(f"/api/reviews/{review}")["json"]
            self.assertIsNone(detail["observations"])
            self.assertIsNone(detail["raw_response"])
            self.assertEqual(detail["allowed_transitions"], [])
            self.assertEqual(detail["evidence"], [])
            self.assertEqual(detail["automated_assessment"]["condition"]["grade"], None)
            self.assertEqual(detail["automated_assessment"]["disposition"]["decision"], "pending_review")
            self.assertEqual(self.request(f"/api/reviews/{review}/images/0")["status"], 404)
            history = self.request(f"/api/reviews/{review}/history")
            self.assertEqual(history["status"], 200)
        with Store(self.database, TenantContext("org_demo_bravo")) as store:
            self.assertEqual(ReviewWorkflow(store).queue(), [])

    def test_demo_startup_never_selects_provider_or_reads_provider_keys(self):
        class SafeEnv(dict):
            def get(self, name, default=None):
                if name in ("GROQ_API_KEY", "GEMINI_API_KEY"):
                    raise AssertionError("provider credential access")
                return super().get(name, default)
        with patch("returns_manager.demo.select_provider", side_effect=AssertionError("provider call")):
            app = dep.create_demo_app(SafeEnv(self.env))
        self.assertEqual(app.config.provider, "disabled")

    def test_local_entry_delegates_without_changing_loopback_config(self):
        with patch.object(ui, "main", return_value=0) as launch:
            self.assertEqual(dep.main(["--organization", "org_demo_alpha", "--reviewer", "TEST"], environ={}), 0)
            self.assertEqual(launch.call_args.args[0][-2:], ["--port", "8000"])
        with patch.object(ui, "main", return_value=0) as launch:
            dep.main(["--port", "9001"], environ={"PORT": "9002"})
            self.assertEqual(launch.call_args.args[0], ["--port", "9001"])
        config = ui.UIConfig(self.database, dep.TENANT, "TEST")
        self.assertEqual(config.authority, "127.0.0.1:8000")
        with self.assertRaises(ui.RequestError):
            ui.UIApplication(config)._boundary({"REMOTE_ADDR": "192.0.2.1", "HTTP_HOST": "demo.example.test"})

    def test_production_server_receives_bounded_settings_and_dynamic_port(self):
        serve = Mock()
        with patch.dict(sys.modules, {"waitress": types.SimpleNamespace(serve=serve)}):
            self.assertEqual(dep.main([], environ=self.env), 0)
        serve.assert_called_once()
        self.assertEqual(serve.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(serve.call_args.kwargs["port"], 9123)
        self.assertEqual(serve.call_args.kwargs["max_request_body_size"], ui.MAX_BODY)
        self.assertTrue(serve.call_args.kwargs["clear_untrusted_proxy_headers"])

    def test_invalid_mode_or_remote_style_cli_configuration_fails_closed(self):
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            self.assertEqual(dep.main([], environ={"DEPLOYMENT_MODE": "unknown"}), 2)
            self.assertEqual(dep.main(["--database", "other.sqlite3"], environ=self.env), 2)

    def test_ui_assets_hide_mutations_and_keep_security_headers(self):
        result = self.request("/assets/workstation.js")
        self.assertEqual(result["status"], 200)
        self.assertIn(b"Boolean(context.read_only)", result["body"])
        self.assertIn("frame-ancestors 'none'", result["headers"]["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", result["headers"])

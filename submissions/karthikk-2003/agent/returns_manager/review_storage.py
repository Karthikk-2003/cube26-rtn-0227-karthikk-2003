"""Scoped review repository over an existing Store connection.

Sources are immutable capture/vision records; review rows reference rather than
copy their evidence. Events are append-only through this API, not cryptographically
immutable. Host access and authentication remain deployment responsibilities.
"""

import json
from dataclasses import asdict
from datetime import datetime, timezone

from .domain import TenantMismatch, ValidationError, identifier
from .observations import text, choice
from .review import HumanDecision, ReviewerContext, STATUSES, TRANSITIONS, route_reasons
from .storage import Store, ConflictError


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _positive_id(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValidationError("positive SQLite integer ID/revision required")


class ReviewWorkflow:
    """Explicit library API; use one instance/connection per local worker.

    The Store's trusted organization/client scope governs every operation. Record
    and unit must also match the stored parent, even when a review ID is known.
    """

    def __init__(self, store: Store):
        if not isinstance(store, Store):
            raise ValidationError("tenant-bound Store required")
        self.store = store
        self._db = store._db
        self._scope = store._scope
        self._db.execute("""CREATE TABLE IF NOT EXISTS review_items (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id TEXT NOT NULL, client_scope TEXT NOT NULL,
            record_id TEXT NOT NULL, unit_id TEXT NOT NULL, source_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (organization_id, client_scope, record_id, unit_id, source_key)
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS review_events (
            review_id INTEGER NOT NULL, revision INTEGER NOT NULL,
            command_id TEXT NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY (review_id, revision), UNIQUE (review_id, command_id)
        )""")
        self._db.commit()

    def _source(self, record_id, unit_id, source_key):
        identifier(record_id, "record_id")
        identifier(unit_id, "unit_id")
        record = self.store.get(record_id)
        if record is None or record["capture"]["unit"]["unit_id"] != unit_id:
            raise TenantMismatch("review source unavailable in this record/unit scope")
        if source_key == "capture":
            return record, None, record["assessment"]
        for attempt in self.store.vision_attempts(record_id):
            if source_key == "vision:" + str(attempt["attempt_id"]):
                return record, attempt["run"], attempt["assessment"]
        raise TenantMismatch("vision attempt unavailable in this record/unit scope")

    def _item(self, review_id, record_id, unit_id):
        _positive_id(review_id)
        identifier(record_id, "record_id")
        identifier(unit_id, "unit_id")
        row = self._db.execute(
            "SELECT source_key, created_at FROM review_items WHERE review_id=? "
            "AND organization_id=? AND client_scope=? AND record_id=? AND unit_id=?",
            (review_id, *self._scope, record_id, unit_id),
        ).fetchone()
        if row is None:
            raise TenantMismatch("review unavailable in this record/unit scope")
        return row

    def _events(self, review_id):
        # Only called after scoped parent authorization; never a public ID-only lookup.
        rows = self._db.execute(
            "SELECT payload FROM review_events WHERE review_id=? ORDER BY revision", (review_id,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def route(self, record_id: str, unit_id: str, *, attempt_id: int | None = None) -> int:
        """Idempotent for one persisted source. A new vision attempt is a new case."""
        if attempt_id is not None:
            _positive_id(attempt_id)
        key = "capture" if attempt_id is None else "vision:" + str(attempt_id)
        record, run, assessment = self._source(record_id, unit_id, key)
        reasons = route_reasons(record["capture"], assessment, run)
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            row = self._db.execute(
                "SELECT review_id FROM review_items WHERE organization_id=? AND client_scope=? "
                "AND record_id=? AND unit_id=? AND source_key=?",
                (*self._scope, record_id, unit_id, key),
            ).fetchone()
            if row:
                return row[0]
            timestamp = _now()
            review_id = self._db.execute(
                "INSERT INTO review_items (organization_id,client_scope,record_id,unit_id,source_key,created_at) "
                "VALUES (?,?,?,?,?,?)", (*self._scope, record_id, unit_id, key, timestamp)
            ).lastrowid
            event = {"revision": 1, "actor_kind": "system", "actor_id": "review-router",
                     "timestamp": timestamp, "reason": "deterministic_review_routing", "previous_state": None,
                     "new_state": {"status": "pending_review", "human_decisions": {}},
                     "uncertainty": reasons, "overrides": [],
                     "assessment_available_at_routing": assessment is not None,
                     "processing_error_at_routing": record["processing_error"]}
            self._db.execute("INSERT INTO review_events VALUES (?,?,?,?,?)",
                             (review_id, 1, "system:route", "{}", _json(event)))
            return review_id

    def history(self, review_id, record_id, unit_id) -> list[dict]:
        self._item(review_id, record_id, unit_id)
        return self._events(review_id)

    def get(self, review_id, record_id, unit_id) -> dict:
        key, created = self._item(review_id, record_id, unit_id)
        record, run, assessment = self._source(record_id, unit_id, key)
        events = self._events(review_id)
        if not events[0]["assessment_available_at_routing"]:
            assessment = None  # Preserve the original interrupted-processing context.
        current = events[-1]
        descriptors = {i["reference"]: i for i in run["images"]} if run else {}
        evidence = []
        for image in record["capture"]["images"]:
            descriptor = descriptors.get(image["reference"])
            evidence.append(descriptor if descriptor else {
                "reference": image["reference"], "evidence_id": None,
                "availability": "missing", "reason": "not_supplied_to_observation_attempt",
            })
        # Human verdicts are visibly attributed and do not alter automated results.
        decisions = current["new_state"]["human_decisions"]
        effective = {}
        for dimension in ("identity", "completeness", "condition", "disposition"):
            result = assessment[dimension] if assessment else {}
            effective[dimension] = {
                "value": result.get("verdict", result.get("decision", "pending_review" if dimension == "disposition" else "UNCERTAIN")),
                "source": "automated" if assessment else "unavailable",
            }
            if dimension in decisions:
                effective[dimension] = {"value": decisions[dimension]["verdict"], "source": "human",
                                        "revision": decisions[dimension]["revision"]}
        return {
            "review_id": review_id, "organization_id": self.store.context.organization_id,
            "client_id": self.store.context.client_id, "record_id": record_id, "unit_id": unit_id,
            "source_key": key, "created_at": created, "updated_at": current["timestamp"],
            "revision": current["revision"], **current["new_state"],
            "uncertainty": events[0]["uncertainty"], "capture": record["capture"],
            "processing_error_at_routing": events[0]["processing_error_at_routing"],
            "evidence": evidence, "raw_response": run["raw_response"] if run else None,
            "observations": run["observations"] if run else None,
            "automated_assessment": assessment, "effective_results": effective,
            "unresolved_decisions": [d for d, r in effective.items() if r["value"] in {"UNCERTAIN", "pending_review"}],
            "business_status": "pending_review",
            "format_notice": "internal_only_not_official_wire_contract",
        }

    def queue(self, *, status: str | None = None) -> list[dict]:
        if status is not None:
            choice(status, STATUSES)
        rows = self._db.execute(
            "SELECT review_id,record_id,unit_id FROM review_items "
            "WHERE organization_id=? AND client_scope=? ORDER BY review_id", self._scope
        ).fetchall()
        items = [self.get(*row) for row in rows]
        return [item for item in items if status is None or item["status"] == status]

    def transition(self, review_id, record_id, unit_id, *, reviewer: ReviewerContext,
                   command_id: str, expected_revision: int, status: str, reason: str,
                   decisions: tuple[HumanDecision, ...] = ()) -> dict:
        """Atomically append a human event. Same command is retry-safe; stale edits fail."""
        self._item(review_id, record_id, unit_id)
        if not isinstance(reviewer, ReviewerContext):
            raise ValidationError("trusted ReviewerContext required")
        ReviewerContext(reviewer.tenant, reviewer.reviewer_id)
        if reviewer.tenant != self.store.context:
            raise TenantMismatch("reviewer organization/client mismatch")
        text(command_id)
        if command_id.startswith("system:"):
            raise ValidationError("reserved internal command ID")
        text(reason)
        choice(status, STATUSES)
        _positive_id(expected_revision)
        if type(decisions) is not tuple or len(decisions) > 2:
            raise ValidationError("at most two independent human decisions required")
        for decision in decisions:
            if not isinstance(decision, HumanDecision):
                raise ValidationError("HumanDecision required; observations cannot be submitted here")
            HumanDecision(decision.dimension, decision.verdict, decision.evidence_refs)
        if len({d.dimension for d in decisions}) != len(decisions):
            raise ValidationError("duplicate decision dimension")
        command = _json({"reviewer": asdict(reviewer), "expected_revision": expected_revision,
                         "status": status, "reason": reason, "decisions": [asdict(d) for d in decisions]})
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            item = self.get(review_id, record_id, unit_id)
            retry = self._db.execute(
                "SELECT command,payload FROM review_events WHERE review_id=? AND command_id=?",
                (review_id, command_id),
            ).fetchone()
            if retry:
                if retry[0] != command:
                    raise ConflictError("command ID reused with different review input")
                return json.loads(retry[1])
            if item["revision"] != expected_revision:
                raise ConflictError("stale review revision")
            if status not in TRANSITIONS[item["status"]]:
                raise ValidationError("invalid internal review status transition")
            if decisions and (item["status"] != "in_review" or status not in {"in_review", "reviewed"}):
                raise ValidationError("human decisions require active review")
            usable = {i["evidence_id"] for i in item["evidence"]
                      if i["availability"] in {"available", "fixture_only"}}
            if any(not set(d.evidence_refs).issubset(usable) for d in decisions):
                raise ValidationError("human decision references unknown/unavailable evidence")
            previous = {"status": item["status"], "human_decisions": item["human_decisions"]}
            revised = dict(item["human_decisions"])
            revision, timestamp = expected_revision + 1, _now()
            overrides = []
            for decision in decisions:
                revised[decision.dimension] = {**asdict(decision), "reviewer_id": reviewer.reviewer_id,
                                              "timestamp": timestamp, "reason": reason, "revision": revision}
                overrides.append({"dimension": decision.dimension,
                                  "previous_result": item["effective_results"][decision.dimension],
                                  "new_verdict": decision.verdict, "evidence_refs": decision.evidence_refs})
            event = {"revision": revision, "actor_kind": "human", "actor_id": reviewer.reviewer_id,
                     "timestamp": timestamp, "reason": reason, "previous_state": previous,
                     "new_state": {"status": status, "human_decisions": revised}, "overrides": overrides}
            self._db.execute("INSERT INTO review_events VALUES (?,?,?,?,?)",
                             (review_id, revision, command_id, command, _json(event)))
            return json.loads(_json(event))

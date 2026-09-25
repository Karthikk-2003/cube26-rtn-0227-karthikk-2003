"""Local synthetic-fixture CLI. No network, image reads or official-contract export."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .domain import TenantContext, ValidationError
from .service import ingest
from .storage import ConflictError, Store
from .validation import parse_record, read_csv


def main() -> int:
    participant = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--organization", required=True, help="Trusted local operator scope, not authentication")
    parser.add_argument("--client", default=None, help="Actual trusted client context only; omitted remains null")
    parser.add_argument("--database", type=Path, default=participant / "runtime" / "returns.sqlite3")
    args = parser.parse_args()
    try:
        database = args.database.resolve()
        if not database.is_relative_to(participant):
            raise ValidationError("database must be inside the participant directory")
        context = TenantContext(args.organization, args.client)
        # Explicit local mixed-tenant fixture selection; never infer caller authority from CSV.
        records = [(row, source) for row, source in read_csv(args.csv)
                   if row["org_id"] == context.organization_id]
        if not records:
            raise ValidationError("no records for selected organization")
        # Validate the complete selected batch before creating/writing a database.
        for row, source in records:
            parse_record(row, context, source)
        database.parent.mkdir(parents=True, exist_ok=True)
        with Store(database, context) as store:
            for row, source in records:
                print(json.dumps(ingest(row, source, store), ensure_ascii=False))
        return 0
    except (ValidationError, ConflictError, OSError, sqlite3.Error) as exc:
        print(f"Phase 1 input/storage error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline annotation CLI. No network, provider selection or business-policy writes."""
import argparse
from dataclasses import asdict
import sqlite3
import sys

from .engine import evaluate, markdown
from .ingestion import (PARTICIPANT, immutable_artifact, load_csv, load_json, persist, read_import)
from .models import AnnotationError, SCHEMA, canonical
from .system import SystemReader


def write_report(report, root):
    json_path = immutable_artifact("reports", canonical(report).encode("utf-8"), ".json", root)
    md_path = immutable_artifact("reports", markdown(report).encode("utf-8"), ".md", root)
    return {"json": json_path.relative_to(root).as_posix(), "markdown": md_path.relative_to(root).as_posix()}


def main(argv=None, *, root=PARTICIPANT):
    root = root.resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema", help="print machine-readable evaluation-only JSON schema")
    for name in ("validate", "import"):
        command = commands.add_parser(name)
        command.add_argument("source", help="participant-relative JSON or annotation CSV")
        command.add_argument("--manifest", help="JSON reference manifest required for CSV")
    command = commands.add_parser("evaluate")
    command.add_argument("imported", help="content-addressed imported dataset path")
    command.add_argument("--database", help="existing participant SQLite file; read-only; no latest-attempt selection")
    command.add_argument("--timestamp", help="explicit UTC report timestamp for deterministic replay")
    command = commands.add_parser("synthetic", help="run isolated synthetic workflow twice; no real inference")
    command.add_argument("--timestamp", help="explicit UTC report timestamp for deterministic replay")
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            print(canonical(SCHEMA), end="")
            return 0
        if args.command in ("validate", "import"):
            imported = load_csv(args.source, args.manifest, root) if args.manifest else load_json(args.source, root)
            result = {"status": "VALID", "kind": imported.dataset.kind, "case_count": len(imported.dataset.cases),
                      "import_id": imported.import_id}
            if args.command == "import":
                result["imported"] = persist(imported, root).relative_to(root).as_posix()
        else:
            if args.command == "synthetic":
                from .fixtures import smoke
                report, imported_path = smoke(args.timestamp, root)
                result = {"repeated_evaluation_identical": True, "imported": imported_path.relative_to(root).as_posix()}
            else:
                imported = read_import(args.imported, root)
                if args.database:
                    with SystemReader(args.database, imported.dataset.tenant, root) as reader:
                        report = evaluate(imported, reader, args.timestamp)
                else:
                    report = evaluate(imported, timestamp=args.timestamp)
                result = {}
            result.update(status="COMPLETE", notice=report["notice"], case_count=report["case_count"],
                          reports=write_report(report, root))
        print(canonical(result), end="")
        return 0
    except AnnotationError as exc:
        print(canonical({"status": "REJECTED", "issues": [asdict(issue) for issue in exc.issues]}), file=sys.stderr, end="")
        return 2
    except (OSError, sqlite3.Error, ValueError, TypeError, RecursionError):
        print(canonical({"status": "REJECTED", "issues": [{"field": "input_or_storage", "code": "unavailable",
            "message": "Check scoped input files, UTF-8 structure and existing database; no source changes were made."}]}),
              file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

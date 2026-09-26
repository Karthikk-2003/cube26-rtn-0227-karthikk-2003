"""Repository sample inventory and blocked visual scenarios, not a label oracle.

The data guide explicitly prohibits treating sample annotations as ground truth.
Filesystem presence checks never read image bytes or establish image ownership.
"""

from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

from .domain import ValidationError, identifier


SCENARIOS = (
    ("correct_product", "Correct returned product"),
    ("wrong_product", "Wrong returned product"),
    ("missing_accessory", "Missing accessory"),
    ("multiple_missing", "Multiple missing components"),
    ("new_looking", "New-looking item"),
    ("lightly_used", "Lightly used item"),
    ("damaged", "Damaged item"),
    ("heavily_damaged", "Heavily damaged item"),
    ("ambiguous_condition", "Ambiguous condition"),
    ("similar_products", "Visually similar products"),
)


def reference_inventory(reference, root: Path, data_parent: Path) -> dict:
    """Check both documented candidate bases; never follow paths outside root."""
    result = {"reference": reference, "status": "unsafe_reference", "checked_paths": [], "present_paths": []}
    try:
        identifier(reference, "photo_ref")
        path = Path(reference)
        if path.is_absolute() or PureWindowsPath(reference).drive or ":" in reference or ".." in path.parts:
            return result
        root = root.resolve()
        for base in (root, data_parent.resolve()):
            candidate = (base / path).resolve()
            if not candidate.is_relative_to(root):
                return result
            relative = candidate.relative_to(root).as_posix()
            if relative not in result["checked_paths"]:
                result["checked_paths"].append(relative)
                if candidate.is_file():
                    result["present_paths"].append(relative)
        result["status"] = "present_unverified" if result["present_paths"] else "missing"
    except (OSError, ValueError, RuntimeError):
        result["status"] = "unavailable"
    return result


def inventory(records, root: Path, csv_path: Path) -> dict:
    """Describe observed annotations exactly; do not infer severity or correctness."""
    units, refs, asins = [], [], defaultdict(set)
    for row, source in records:
        images = [reference_inventory(ref, root, csv_path.parent)
                  for ref in row["photo_refs"].split(";") if ref]
        refs.extend(images)
        asins[row["ordered_asin"]].add(row["ordered_sku"])
        units.append({"organization_id": row["org_id"], "unit_id": row["unit_id"], "record_id": row["record_id"],
                      "row_number": source.row_number, "images": images,
                      "annotations_not_ground_truth": {key: row[key] for key in (
                          "identity_match", "parts_list", "parts_missing", "observed_state",
                          "amazon_condition", "operator_disposition")}})
    rows = [row for row, _ in records]
    distribution = lambda field: dict(sorted(Counter(row[field] for row in rows).items()))
    return {
        "kind": "synthetic_repository_sample_not_benchmark", "input_path": csv_path.relative_to(root).as_posix(),
        "authority": "data/README.md: DUMMY DATA; do not treat as ground truth; eval set is separate",
        "rows": len(rows), "unique_units": len({r["unit_id"] for r in rows}),
        "unique_scoped_records": len({(r["org_id"], r["record_id"]) for r in rows}),
        "organizations": distribution("org_id"), "identity_annotations": distribution("identity_match"),
        "condition_annotations_nonempty": sum(bool(r["amazon_condition"]) for r in rows),
        "condition_annotations_blank": sum(not r["amazon_condition"] for r in rows),
        "parts_expectations_rows": sum(bool(r["parts_list"]) for r in rows),
        "missing_parts_annotation_rows": sum(bool(r["parts_missing"]) for r in rows),
        "observed_state_annotations": distribution("observed_state"),
        "disposition_annotations": distribution("operator_disposition"),
        "image_references": len(refs), "unique_image_references": len({r["reference"] for r in refs}),
        "image_reference_status": dict(sorted(Counter(r["status"] for r in refs).items())),
        "client_context": "not_supplied_by_sample", "authoritative_ground_truth": "unavailable",
        "condition_definitions": "BLOCKED: no complete applicable condition policy in repository",
        "disposition_mapping": "BLOCKED: no authoritative condition-to-disposition policy",
        "asin_to_multiple_skus": {key: sorted(value) for key, value in sorted(asins.items()) if len(value) > 1},
        "units": units,
    }


def scenario_cases(dataset: dict) -> list[dict]:
    def candidates(key, annotation):
        missing = [part for part in annotation["parts_missing"].split(";") if part]
        return {
            "correct_product": annotation["identity_match"] == "yes",
            "wrong_product": annotation["identity_match"] == "no",
            "missing_accessory": len(missing) == 1,
            "multiple_missing": len(missing) > 1,
            "new_looking": annotation["observed_state"] in {"factory_sealed", "opened_unused"},
            "lightly_used": annotation["observed_state"] == "signs_of_use",
            "damaged": annotation["observed_state"] == "damaged",
            # No severity or visual similarity can be inferred from sample annotations.
            "heavily_damaged": False,
            "ambiguous_condition": annotation["observed_state"] == "uncertain",
            "similar_products": False,
        }[key]

    cases = []
    for key, name in SCENARIOS:
        selected = [unit for unit in dataset["units"] if candidates(key, unit["annotations_not_ground_truth"])]
        cases.append({
            "case_id": "scenario:" + key, "category": "visual_scenario", "scenario": name,
            "organization_id": None, "unit_id": None, "record_id": None,
            "input_reference": dataset["input_path"] + " (inventory only)",
            "expected": None, "actual": None, "status": "BLOCKED", "system_state": "NOT_RUN",
            "evidence": [{"organization_id": unit["organization_id"], "unit_id": unit["unit_id"],
                          "record_id": unit["record_id"], "images": unit["images"]} for unit in selected],
            "annotation_candidate_count": len(selected),
            "candidate_notice": "Synthetic annotation candidates only; neither confirmed scenarios nor labels. "
                                "Signs of use do not establish light use; listed missing parts need not be accessories.",
            "ground_truth": "unavailable", "final_business_decision_evaluable": False,
            "uncertainty": ["genuine_return_and_reference_images_unavailable",
                            "independent_authoritative_labels_unavailable", "real_provider_not_implemented",
                            "condition_and_disposition_policy_unresolved"],
            "failure_reason": None,
            "blocked_reason": "No genuine image-backed, independently labelled scenario set. Sample annotations "
                              "are expressly non-authoritative; fixture parser tests do not establish visual accuracy.",
        })
    return cases

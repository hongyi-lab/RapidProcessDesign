"""Offline audit of supplied held-out reference/prediction pairs; no training.

JSON inputs are intentionally strict about sample/group membership and declared
provenance. Declarations are recorded evidence, not proof that an operator never
looked at a protected set. This tool does not generate prediction intervals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

SCHEMA_VERSION = "bwb-uq-offline-v1"
SPLITS = ("proper_train", "validation", "calibration", "test")
LIMITATIONS = [
    "Metrics compare the surrogate with the declared reference fidelity, not with a real aircraft.",
    "Empirical marginal coverage is not a per-candidate, multi-output, multi-condition or aircraft-feasibility guarantee.",
    "Optimization-selected rows are reported separately; exchangeability is not asserted after optimization.",
    "Split and protection declarations are checked for consistency; their real-world truth requires independent evidence review.",
]


class EvaluationError(ValueError):
    pass


def _required(condition, reason):
    if not condition:
        raise EvaluationError(reason)


def _text(value, name):
    _required(isinstance(value, str) and bool(value.strip()), "nonempty_string_required:" + name)
    return value


def _number(value, name):
    _required(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value), "finite_number_required:" + name)
    return float(value)


def _identity(row):
    _required(isinstance(row, dict), "sample_object_required")
    return _text(row.get("sample_id"), "sample_id"), _text(row.get("group_id"), "group_id")


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _index(rows, name):
    _required(isinstance(rows, list), "array_required:" + name)
    result = {}
    for row in rows:
        sid, _ = _identity(row)
        _required(sid not in result, "duplicate_sample:" + name + ":" + sid)
        result[sid] = row
    return result


def validate_manifest(manifest):
    _required(isinstance(manifest, dict), "manifest_object_required")
    _required(manifest.get("schema_version") == SCHEMA_VERSION, "unsupported_manifest_schema")
    for section in ("dataset", "model", "splits", "protection"):
        _required(isinstance(manifest.get(section), dict), "object_required:" + section)
    dataset, model = manifest["dataset"], manifest["model"]
    for key in ("id", "version", "reference_fidelity"):
        _text(dataset.get(key), "dataset." + key)
    for key in ("id", "version"):
        _text(model.get(key), "model." + key)
    _required(set(manifest["splits"]) == set(SPLITS), "exact_four_splits_required")
    indexes = {name: _index(manifest["splits"][name], name) for name in SPLITS}
    _required(bool(indexes["test"]), "nonempty_test_required")
    for i, name in enumerate(SPLITS):
        for other in SPLITS[i + 1:]:
            _required(not (set(indexes[name]) & set(indexes[other])), "sample_split_overlap:" + name + ":" + other)
            groups = {v["group_id"] for v in indexes[name].values()}
            other_groups = {v["group_id"] for v in indexes[other].values()}
            _required(not (groups & other_groups), "group_split_overlap:" + name + ":" + other)
    protection = manifest["protection"]
    for key in ("splits_frozen_before_fitting", "calibration_not_used_for_tuning_or_preprocessing", "test_not_used_for_tuning_calibration_or_selection"):
        _required(protection.get(key) is True, "protected_set_declaration_required:" + key)
    _text(protection.get("evidence_id"), "protection.evidence_id")
    provenance = model.get("training_provenance")
    _required(isinstance(provenance, dict) and provenance.get("status") == "known", "unknown_training_provenance")
    _required(provenance.get("complete_exposure_list") is True, "complete_training_and_tuning_exposure_required")
    _text(provenance.get("evidence_id"), "training_provenance.evidence_id")
    seen = _index(provenance.get("seen_samples"), "training_exposure")
    for sid, row in indexes["proper_train"].items():
        _required(sid in seen and seen[sid]["group_id"] == row["group_id"], "proper_train_missing_from_provenance:" + sid)
    exposed_groups = {v["group_id"] for v in seen.values()}
    for split in ("calibration", "test"):
        _required(not (set(seen) & set(indexes[split])), "pretraining_sample_leakage:" + split)
        _required(not (exposed_groups & {v["group_id"] for v in indexes[split].values()}), "pretraining_group_leakage:" + split)
    return indexes


def _metrics(rows, nominal):
    n = len(rows)
    if not n:
        return {"n": 0, "mae": None, "rmse": None, "coverage": None, "mean_interval_width": None, "interval_score": None}
    errors = [r["mean"] - r["reference"] for r in rows]
    out = {"n": n, "mae": sum(abs(e) for e in errors) / n, "rmse": math.sqrt(sum(e * e for e in errors) / n), "coverage": None, "mean_interval_width": None, "interval_score": None}
    if nominal is not None:
        alpha = 1 - nominal
        widths = [r["upper"] - r["lower"] for r in rows]
        scores = [width + 2 / alpha * max(r["lower"] - r["reference"], 0) + 2 / alpha * max(r["reference"] - r["upper"], 0) for width, r in zip(widths, rows)]
        out.update(coverage=sum(r["lower"] <= r["reference"] <= r["upper"] for r in rows) / n, mean_interval_width=sum(widths) / n, interval_score=sum(scores) / n)
    return out


def evaluate(manifest=None, reference=None, predictions=None):
    """Return audited test metrics; malformed or leaking supplied inputs raise."""
    if manifest is None and reference is None and predictions is None:
        return {"schema_version": SCHEMA_VERSION, "status": "not_evaluated", "reason": "independent_reference_predictions_and_split_manifest_not_supplied", "metrics": None, "uncertainty_metadata": None, "limitations": LIMITATIONS}
    _required(all(v is not None for v in (manifest, reference, predictions)), "all_three_inputs_required")
    indexes = validate_manifest(manifest)
    refs = _index(reference, "reference")
    _required(isinstance(predictions, dict), "predictions_object_required")
    preds = _index(predictions.get("rows"), "predictions")
    _required(set(refs) == set(indexes["test"]) == set(preds), "reference_and_prediction_must_cover_exact_test_set")
    meta = predictions.get("metadata")
    _required(isinstance(meta, dict), "prediction_metadata_required")
    for key, expected in (("model_id", manifest["model"]["id"]), ("model_version", manifest["model"]["version"]), ("dataset_id", manifest["dataset"]["id"]), ("dataset_version", manifest["dataset"]["version"]), ("reference_fidelity", manifest["dataset"]["reference_fidelity"])):
        _required(meta.get(key) == expected, "prediction_identity_mismatch:" + key)
    _text(meta.get("prediction_run_id"), "prediction_run_id")
    _text(meta.get("predictions_frozen_before_test_labels_evidence_id"), "predictions_frozen_before_test_labels_evidence_id")
    intervals, nominal = meta.get("intervals"), None
    if intervals is not None:
        _required(isinstance(intervals, dict), "interval_metadata_object_required")
        _required(intervals.get("type") == "prediction_interval", "only_prediction_intervals_supported")
        nominal = _number(intervals.get("nominal_level"), "nominal_level")
        _required(0 < nominal < 1, "nominal_level_must_be_between_zero_and_one")
        _text(intervals.get("distribution_statement"), "distribution_statement")
        calibration = intervals.get("calibration")
        _required(isinstance(calibration, dict), "calibration_metadata_required")
        for key in ("method", "data_version", "evidence_id"):
            _text(calibration.get(key), "calibration." + key)
        ncal = calibration.get("sample_count")
        _required(type(ncal) is int and ncal == len(indexes["calibration"]), "calibration_count_mismatch")
        _required(calibration["method"] == "none" or ncal > 0, "calibration_samples_required")
    quantity_rows, units = {}, {}
    for sid, ref in refs.items():
        pred = preds[sid]
        for row in (ref, pred):
            _required(row["group_id"] == indexes["test"][sid]["group_id"], "group_identity_mismatch:" + sid)
        _required(ref.get("domain_group") in ("in_domain", "boundary", "out_of_domain", "unknown"), "domain_group_required:" + sid)
        _required(type(ref.get("optimization_selected")) is bool, "optimization_selected_flag_required:" + sid)
        rq, pq, ru = ref.get("quantities"), pred.get("quantities"), ref.get("units")
        _required(isinstance(rq, dict) and bool(rq) and isinstance(pq, dict) and isinstance(ru, dict), "quantity_objects_required:" + sid)
        _required(set(rq) == set(pq) == set(ru), "quantity_or_unit_mismatch:" + sid)
        if quantity_rows:
            _required(set(rq) == set(quantity_rows), "all_test_rows_must_have_same_quantities")
        for quantity, reference_value in rq.items():
            unit = _text(ru[quantity], "unit:" + quantity)
            _required(quantity not in units or units[quantity] == unit, "mixed_units:" + quantity)
            units[quantity] = unit
            item = pq[quantity]
            _required(isinstance(item, dict) and not (set(item) - {"mean", "lower", "upper"}), "prediction_quantity_schema:" + quantity)
            row = {"reference": _number(reference_value, sid + ":reference"), "mean": _number(item.get("mean"), sid + ":mean"), "domain_group": ref["domain_group"], "optimization_selected": ref["optimization_selected"]}
            if intervals is not None:
                row.update(lower=_number(item.get("lower"), sid + ":lower"), upper=_number(item.get("upper"), sid + ":upper"))
                _required(row["lower"] <= row["upper"], "reversed_interval:" + sid)
            else:
                _required(item.get("lower") is None and item.get("upper") is None, "bounds_require_interval_metadata")
            quantity_rows.setdefault(quantity, []).append(row)
    results = {}
    for quantity, rows in quantity_rows.items():
        results[quantity] = {"unit": units[quantity], "reference_fidelity": manifest["dataset"]["reference_fidelity"], "nominal_level": nominal, "overall": _metrics(rows, nominal), "by_domain": {domain: _metrics([r for r in rows if r["domain_group"] == domain], nominal) for domain in ("in_domain", "boundary", "out_of_domain", "unknown")}, "by_selection": {label: _metrics([r for r in rows if r["optimization_selected"] == selected], nominal) for label, selected in (("optimization_selected", True), ("not_optimization_selected", False))}, "selected_by_domain": {domain: _metrics([r for r in rows if r["optimization_selected"] and r["domain_group"] == domain], nominal) for domain in ("in_domain", "boundary", "out_of_domain", "unknown")}}
    return {"schema_version": SCHEMA_VERSION, "status": "evaluated_against_declared_reference", "metrics": results, "uncertainty_metadata": intervals, "interval_reason": None if intervals else "no_intervals_supplied_point_error_only", "input_sha256": {"manifest": _sha(manifest), "reference": _sha(reference), "predictions": _sha(predictions)}, "dataset": manifest["dataset"], "model": manifest["model"], "prediction_run_id": meta["prediction_run_id"], "protection": manifest["protection"], "split_counts": {k: len(v) for k, v in indexes.items()}, "evidence_review_status": "operator_declarations_not_independently_verified", "limitations": LIMITATIONS}


def schema_example():
    """Empty template only; placeholders intentionally fail an empirical audit."""
    return {
        "note": "SCHEMA TEMPLATE ONLY: no real data or successful assessment is supplied. Populate the complete membership/evidence before evaluation.",
        "manifest": {"schema_version": SCHEMA_VERSION, "dataset": {"id": "REPLACE", "version": "REPLACE", "reference_fidelity": "REPLACE: measured/CFD/low-order/surrogate"}, "model": {"id": "REPLACE", "version": "REPLACE", "training_provenance": {"status": "unknown", "complete_exposure_list": False, "evidence_id": None, "seen_samples": []}}, "splits": {s: [] for s in SPLITS}, "protection": {"splits_frozen_before_fitting": False, "calibration_not_used_for_tuning_or_preprocessing": False, "test_not_used_for_tuning_calibration_or_selection": False, "evidence_id": None}},
        "reference": [], "reference_row_schema": {"sample_id": "string", "group_id": "geometry/family identifier", "domain_group": "in_domain|boundary|out_of_domain|unknown", "optimization_selected": "boolean", "quantities": {"CL": "finite reference number"}, "units": {"CL": "dimensionless"}},
        "predictions": {"metadata": {"model_id": "REPLACE", "model_version": "REPLACE", "dataset_id": "REPLACE", "dataset_version": "REPLACE", "reference_fidelity": "REPLACE", "prediction_run_id": "REPLACE", "predictions_frozen_before_test_labels_evidence_id": None, "intervals": None}, "rows": []},
        "prediction_row_schema": {"sample_id": "string", "group_id": "string", "quantities": {"CL": {"mean": "finite number", "lower": None, "upper": None}}},
        "optional_interval_metadata_schema": {"type": "prediction_interval", "nominal_level": "number strictly between 0 and 1", "distribution_statement": "explicit applicability and exchangeability assumptions", "calibration": {"method": "method name or none", "sample_count": "integer matching calibration split", "data_version": "string", "evidence_id": "string"}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--schema-example", action="store_true")
    args = parser.parse_args()
    try:
        read = lambda p: json.loads(p.read_text(encoding="utf-8")) if p else None
        result = schema_example() if args.schema_example else evaluate(read(args.manifest), read(args.reference), read(args.predictions))
        exit_code = 0
    except (EvaluationError, OSError, json.JSONDecodeError) as exc:
        result = {"schema_version": SCHEMA_VERSION, "status": "rejected", "reason": str(exc), "metrics": None, "limitations": LIMITATIONS}
        exit_code = 2
    output = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

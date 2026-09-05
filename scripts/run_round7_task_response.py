"""Run the reproducible Round 7 Mission Demo task-response audit.

The audit deliberately uses the checked-in Demo profile, its fixed seed and the
current evaluator.  It does not tune coefficients, widen bounds, or inject any
mission-to-geometry rules.  Each case stores the complete raw search result plus
the fixed-candidate comparison needed to separate mission response from search
pool response.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api.app.services.rapid_design.config_loader import (
    load_mission_demo_profile,
    mission_demo_profile_hash,
    validated_mission_demo_inputs,
)
from services.api.app.services.rapid_design.mission_demo import (
    evaluate_mission_demo_candidate,
    search_mission_demo,
)


@dataclass(frozen=True)
class CaseDefinition:
    case_id: str
    label: str
    preset_id: str
    kind: str
    changed_inputs: dict[str, float]
    expected_mechanisms: tuple[str, ...]


def _case_definitions() -> list[CaseDefinition]:
    return [
        CaseDefinition(
            "baseline_long_endurance",
            "Long-endurance preset / baseline mission",
            "long_endurance_uav",
            "preset_baseline",
            {},
            (),
        ),
        CaseDefinition(
            "baseline_fast_cruise",
            "Fast-cruise preset / baseline mission",
            "fast_cruise_recon",
            "preset_baseline",
            {},
            (),
        ),
        CaseDefinition(
            "baseline_payload_utility",
            "Payload-utility preset / baseline mission",
            "payload_utility",
            "preset_baseline",
            {},
            (),
        ),
        CaseDefinition(
            "vary_required_range",
            "Change required range only",
            "long_endurance_uav",
            "single_input",
            {"required_range_km": 1800.0},
            ("constraint_threshold",),
        ),
        CaseDefinition(
            "vary_payload_mass",
            "Change payload mass only",
            "long_endurance_uav",
            "single_input",
            {"payload_mass_kg": 300.0},
            ("model_calculation",),
        ),
        CaseDefinition(
            "vary_cruise_speed",
            "Change cruise speed only",
            "long_endurance_uav",
            "single_input",
            {"cruise_speed_kmh": 320.0},
            ("analysis_condition", "model_calculation"),
        ),
        CaseDefinition(
            "vary_cruise_altitude",
            "Change cruise altitude only",
            "long_endurance_uav",
            "single_input",
            {"cruise_altitude_m": 6000.0},
            ("analysis_condition", "model_calculation"),
        ),
        CaseDefinition(
            "vary_max_fuel",
            "Change maximum fuel only",
            "long_endurance_uav",
            "single_input",
            {"max_fuel_mass_kg": 200.0},
            ("constraint_threshold", "sampling_range"),
        ),
        CaseDefinition(
            "vary_max_takeoff_mass",
            "Change maximum takeoff mass only",
            "long_endurance_uav",
            "single_input",
            {"max_takeoff_mass_kg": 900.0},
            ("constraint_threshold", "objective_normalization"),
        ),
        CaseDefinition(
            "vary_target_lift_to_drag",
            "Change target lift-to-drag only",
            "long_endurance_uav",
            "single_input",
            {"target_lift_to_drag": 16.5},
            ("constraint_threshold",),
        ),
        CaseDefinition(
            "difficult_task",
            "Difficult but configuration-valid mission",
            "long_endurance_uav",
            "difficult",
            {
                "required_range_km": 1800.0,
                "payload_mass_kg": 250.0,
                "cruise_speed_kmh": 280.0,
                "cruise_altitude_m": 6000.0,
                "max_fuel_mass_kg": 500.0,
                "max_takeoff_mass_kg": 1800.0,
                "target_lift_to_drag": 18.0,
            },
            (
                "constraint_threshold",
                "analysis_condition",
                "model_calculation",
                "sampling_range",
            ),
        ),
        CaseDefinition(
            "no_feasible_task",
            "Configuration-valid deliberately infeasible mission",
            "long_endurance_uav",
            "no_feasible",
            {
                "required_range_km": 3000.0,
                "payload_mass_kg": 500.0,
                "cruise_speed_kmh": 80.0,
                "cruise_altitude_m": 11000.0,
                "max_fuel_mass_kg": 25.0,
                "max_takeoff_mass_kg": 300.0,
                "target_lift_to_drag": 40.0,
            },
            (
                "constraint_threshold",
                "analysis_condition",
                "model_calculation",
                "sampling_range",
            ),
        ),
    ]


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _git_value(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def _changed_numeric_keys(
    baseline: dict[str, Any], changed: dict[str, Any], *, tolerance: float = 1e-9
) -> list[str]:
    keys: list[str] = []
    for key in sorted(set(baseline) | set(changed)):
        left = baseline.get(key)
        right = changed.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if abs(float(left) - float(right)) > tolerance:
                keys.append(key)
        elif left != right:
            keys.append(key)
    return keys


def _constraints_by_name(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["name"]): item
        for item in candidate.get("constraints", [])
        if isinstance(item, dict) and "name" in item
    }


def _candidate_signature(candidate: dict[str, Any]) -> str:
    return _json_text(
        {
            "design": candidate.get("design"),
            "sizing": candidate.get("sizing"),
            "geometry_fingerprint": candidate.get("geometry_fingerprint"),
        }
    )


def _record_payload(record: dict[str, Any]) -> dict[str, Any]:
    nested = record.get("candidate")
    return nested if isinstance(nested, dict) else record


def _pool_signatures(result: dict[str, Any]) -> list[str]:
    signatures: list[str] = []
    for record in result.get("search", {}).get("records", []):
        if not isinstance(record, dict) or not record.get("valid", True):
            continue
        payload = _record_payload(record)
        if payload.get("design") is not None:
            signatures.append(_candidate_signature(payload))
    return signatures


def _top_signatures(result: dict[str, Any]) -> list[str]:
    return [_candidate_signature(candidate) for candidate in result.get("candidates", [])]


def _fixed_comparison(
    *,
    baseline: dict[str, Any],
    changed: dict[str, Any],
    changed_inputs: dict[str, float],
) -> dict[str, Any]:
    baseline_constraints = _constraints_by_name(baseline)
    changed_constraints = _constraints_by_name(changed)
    constraint_changes: list[dict[str, object]] = []
    for name in sorted(set(baseline_constraints) | set(changed_constraints)):
        before = baseline_constraints.get(name, {})
        after = changed_constraints.get(name, {})
        changed_fields = [
            key
            for key in ("actual", "limit", "margin", "satisfied")
            if before.get(key) != after.get(key)
        ]
        if changed_fields:
            constraint_changes.append(
                {
                    "name": name,
                    "changed_fields": changed_fields,
                    "before": {key: before.get(key) for key in changed_fields},
                    "after": {key: after.get(key) for key in changed_fields},
                    "satisfied_before": before.get("satisfied"),
                    "satisfied_after": after.get("satisfied"),
                }
            )
    return {
        "changed_inputs": changed_inputs,
        "same_design": baseline.get("design") == changed.get("design"),
        "same_sizing": baseline.get("sizing") == changed.get("sizing"),
        "same_geometry_state": baseline.get("geometry_state") == changed.get("geometry_state"),
        "same_geometry_fingerprint": baseline.get("geometry_fingerprint")
        == changed.get("geometry_fingerprint"),
        "same_design_hash": baseline.get("design_hash") == changed.get("design_hash"),
        "changed_condition_keys": _changed_numeric_keys(
            baseline.get("condition", {}), changed.get("condition", {})
        ),
        "changed_metric_keys": _changed_numeric_keys(
            baseline.get("metrics", {}), changed.get("metrics", {})
        ),
        "constraint_changes": constraint_changes,
        "objective_before": baseline.get("objective"),
        "objective_after": changed.get("objective"),
        "objective_changed": baseline.get("objective") != changed.get("objective"),
        "feasible_before": baseline.get("feasible"),
        "feasible_after": changed.get("feasible"),
        "cruise_consistency_before": baseline.get("cruise_consistency"),
        "cruise_consistency_after": changed.get("cruise_consistency"),
    }


def _observed_response(
    *,
    definition: CaseDefinition,
    inputs: dict[str, float],
    baseline_inputs: dict[str, float],
    result: dict[str, Any],
    baseline_result: dict[str, Any],
    fixed_comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    forwarded = all(result.get("inputs", {}).get(key) == value for key, value in inputs.items())
    categories: list[str] = []
    if fixed_comparison:
        if any(
            "limit" in change.get("changed_fields", [])
            for change in fixed_comparison["constraint_changes"]
        ):
            categories.append("constraint_threshold")
        if fixed_comparison["changed_condition_keys"]:
            categories.append("analysis_condition")
        if fixed_comparison["changed_metric_keys"]:
            categories.append("model_calculation")
        if (
            fixed_comparison["objective_changed"]
            and "max_takeoff_mass_kg" in definition.changed_inputs
        ):
            categories.append("objective_normalization")
    if "max_fuel_mass_kg" in definition.changed_inputs:
        categories.append("sampling_range")
    if not categories and definition.kind == "single_input":
        categories.append("input_recorded_but_no_observed_downstream_effect")

    top_changed = _top_signatures(result) != _top_signatures(baseline_result)
    pool_changed = _pool_signatures(result) != _pool_signatures(baseline_result)
    rank_ids = [item.get("candidate_id") for item in result.get("candidates", [])]
    baseline_rank_ids = [item.get("candidate_id") for item in baseline_result.get("candidates", [])]
    ranking_changed = rank_ids != baseline_rank_ids
    inactive_thresholds = []
    if fixed_comparison:
        inactive_thresholds = [
            str(change["name"])
            for change in fixed_comparison["constraint_changes"]
            if "limit" in change.get("changed_fields", [])
            and change.get("satisfied_before") is True
            and change.get("satisfied_after") is True
        ]
        if inactive_thresholds:
            categories.append("constraint_inactive_for_fixed_candidate")
            if not ranking_changed:
                categories.append("constraint_inactive_ranking_unchanged")
    expected = set(definition.expected_mechanisms)
    observed = set(categories)
    missing = sorted(expected - observed)
    bug = not forwarded or bool(missing)
    if not ranking_changed:
        categories.append("ranking_unchanged")
    return {
        "input_forwarded": forwarded,
        "expected_mechanisms": list(definition.expected_mechanisms),
        "observed_categories": categories,
        "missing_expected_mechanisms": missing,
        "possible_parameter_or_state_bug": bug,
        "candidate_pool_changed": pool_changed,
        "top_k_changed": top_changed,
        "ranking_changed": ranking_changed,
        "inactive_fixed_candidate_constraints": inactive_thresholds,
        "ranking_unchanged_reason": (
            "changed_constraint_not_activated_for_fixed_candidate_and_top_k_stable"
            if not ranking_changed and inactive_thresholds
            else (
                "model_response_changed_but_top_k_order_stable"
                if not ranking_changed and "model_calculation" in observed
                else None
            )
        ),
        "baseline_inputs": baseline_inputs,
        "case_inputs": inputs,
        "interpretation": (
            "parameter_or_state_bug"
            if bug
            else (
                "response_observed_but_ranking_unchanged"
                if not ranking_changed
                else "response_and_ranking_change_observed"
            )
        ),
    }


def _constraint_margin(candidate: dict[str, Any], name: str) -> object:
    return _constraints_by_name(candidate).get(name, {}).get("margin", "")


def _qualification(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("qualification", {})
    return value if isinstance(value, dict) else {}


def _selection(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("selection", {})
    return value if isinstance(value, dict) else {}


def _candidate_row(case: dict[str, Any], candidate: dict[str, Any]) -> dict[str, object]:
    result = case["result"]
    qualification = _qualification(candidate)
    selection = _selection(candidate)
    cruise = candidate.get("cruise_consistency", {})
    if not isinstance(cruise, dict):
        cruise = {}
    cruise_comparison = cruise.get("comparison", {})
    if not isinstance(cruise_comparison, dict):
        cruise_comparison = {}
    metrics = candidate.get("metrics", {})
    return {
        "case_id": case["case"]["case_id"],
        "preset_id": case["case"]["preset_id"],
        "profile_id": result.get("profile", {}).get("id"),
        "profile_version": result.get("profile", {}).get("version"),
        "profile_hash": result.get("profile", {}).get("hash"),
        "seed": result.get("search", {}).get("seed"),
        "rank": candidate.get("rank"),
        "candidate_id": candidate.get("candidate_id"),
        "geometry_fingerprint": candidate.get("geometry_fingerprint"),
        "design_hash": candidate.get("design_hash"),
        "geometry_valid": qualification.get("geometry_valid", True),
        "demo_constraints_satisfied": qualification.get(
            "demo_constraints_satisfied", candidate.get("feasible")
        ),
        "engineering_validation": qualification.get("engineering_validation", "not_performed"),
        "feasible": candidate.get("feasible"),
        "objective": candidate.get("objective"),
        "selection_reason_code": selection.get("reason_code", ""),
        "selection_explanation": selection.get("explanation", ""),
        "takeoff_mass_kg": metrics.get("takeoff_mass_kg"),
        "empty_mass_kg": metrics.get("empty_mass_kg"),
        "fuel_mass_kg": metrics.get("fuel_mass_kg"),
        "achieved_range_km": metrics.get("achieved_range_km"),
        "max_lift_to_drag": metrics.get("max_lift_to_drag"),
        "range_margin": _constraint_margin(candidate, "range"),
        "lift_to_drag_margin": _constraint_margin(candidate, "lift_to_drag"),
        "takeoff_mass_margin": _constraint_margin(candidate, "takeoff_mass"),
        "fuel_mass_margin": _constraint_margin(candidate, "fuel_mass"),
        "cruise_diagnostic_status": cruise.get("status"),
        "required_cl": cruise.get("required_cl"),
        "matched_ld": cruise_comparison.get("ld_at_reference_state"),
        "max_ld": cruise_comparison.get("max_ld", metrics.get("max_lift_to_drag")),
        "design_json": _json_text(candidate.get("design", {})),
        "sizing_json": _json_text(candidate.get("sizing", {})),
        "score_breakdown_json": _json_text(candidate.get("score_breakdown", {})),
        "constraints_json": _json_text(candidate.get("constraints", [])),
    }


def _evaluation_row(case: dict[str, Any], record: dict[str, Any]) -> dict[str, object]:
    payload = _record_payload(record)
    candidate_id = payload.get("candidate_id", record.get("candidate_id"))
    decision = next(
        (
            item
            for item in case["result"].get("selection", {}).get("decisions", [])
            if isinstance(item, dict) and item.get("candidate_id") == candidate_id
        ),
        {},
    )
    return {
        "case_id": case["case"]["case_id"],
        "preset_id": case["case"]["preset_id"],
        "evaluation": record.get("evaluation", record.get("index")),
        "valid": record.get("valid"),
        "error": record.get("error", record.get("reason", "")),
        "elapsed_ms": record.get("elapsed_ms", record.get("timing_ms", "")),
        "candidate_id": candidate_id,
        "geometry_fingerprint": payload.get("geometry_fingerprint"),
        "design_hash": payload.get("design_hash"),
        "feasible": payload.get("feasible"),
        "objective": payload.get("objective"),
        "selected": decision.get("selected", ""),
        "selected_rank": decision.get("selected_rank", ""),
        "ranked_position": decision.get("ranked_position", ""),
        "selection_reason": decision.get("reason_code", ""),
        "selection_explanation": decision.get("explanation", ""),
        "design_json": _json_text(payload.get("design", {})),
        "sizing_json": _json_text(payload.get("sizing", {})),
        "score_breakdown_json": _json_text(payload.get("score_breakdown", {})),
        "constraints_json": _json_text(payload.get("constraints", [])),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="New directory for this run (default: artifacts/round7-task-response/<UTC timestamp>)",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        arguments.output_dir
        if arguments.output_dir is not None
        else PROJECT_ROOT / "artifacts" / "round7-task-response" / timestamp
    ).resolve()
    if output_dir.exists():
        print(f"Refusing to overwrite existing output directory: {output_dir}", file=sys.stderr)
        return 2
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True)

    profile = load_mission_demo_profile()
    profile_hash = mission_demo_profile_hash(profile)
    baseline_inputs = validated_mission_demo_inputs(profile, {})
    definitions = _case_definitions()
    print(
        f"Round 7 task-response audit: {len(definitions)} cases, "
        f"seed={profile.optimizer.seed}, profile={profile.profile_id}/{profile.profile_version}"
    )

    completed_cases: list[dict[str, Any]] = []
    baseline_result: dict[str, Any] | None = None
    baseline_candidate: dict[str, Any] | None = None
    baseline_fixed: dict[str, Any] | None = None

    for case_number, definition in enumerate(definitions, start=1):
        inputs = {**baseline_inputs, **definition.changed_inputs}
        validated = validated_mission_demo_inputs(profile, inputs)
        print(f"[{case_number:02d}/{len(definitions):02d}] {definition.case_id}: starting")

        last_reported = 0

        def report_progress(
            completed: int,
            total: int,
            _record: dict[str, object],
            case_index: int = case_number,
            case_id: str = definition.case_id,
            case_total: int = len(definitions),
        ) -> None:
            nonlocal last_reported
            if completed == total or completed - last_reported >= 4:
                print(
                    f"[{case_index:02d}/{case_total:02d}] "
                    f"{case_id}: {completed}/{total} evaluations"
                )
                last_reported = completed

        started = time.perf_counter()
        result = search_mission_demo(
            job_id=f"round7-{definition.case_id}",
            family_id="conventional_v2",
            preset_id=definition.preset_id,
            inputs=validated,
            profile=profile,
            on_progress=report_progress,
        )
        measured_elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

        fixed_candidate: dict[str, Any] | None = None
        fixed_comparison: dict[str, Any] | None = None
        response: dict[str, Any] | None = None
        if definition.case_id == "baseline_long_endurance":
            if not result.get("candidates"):
                raise RuntimeError(
                    "baseline search returned no candidate for fixed-candidate audit"
                )
            baseline_result = result
            baseline_candidate = result["candidates"][0]
            baseline_fixed = evaluate_mission_demo_candidate(
                profile=profile,
                family_id="conventional_v2",
                preset_id=definition.preset_id,
                design=baseline_candidate["design"],
                sizing=baseline_candidate["sizing"],
                inputs=validated,
            )
            fixed_candidate = baseline_fixed
        elif definition.preset_id == "long_endurance_uav" and baseline_candidate is not None:
            fixed_candidate = evaluate_mission_demo_candidate(
                profile=profile,
                family_id="conventional_v2",
                preset_id=definition.preset_id,
                design=baseline_candidate["design"],
                sizing=baseline_candidate["sizing"],
                inputs=validated,
            )
            assert baseline_fixed is not None
            fixed_comparison = _fixed_comparison(
                baseline=baseline_fixed,
                changed=fixed_candidate,
                changed_inputs=definition.changed_inputs,
            )
            assert baseline_result is not None
            response = _observed_response(
                definition=definition,
                inputs=validated,
                baseline_inputs=baseline_inputs,
                result=result,
                baseline_result=baseline_result,
                fixed_comparison=fixed_comparison,
            )

        case_payload = {
            "case": asdict(definition),
            "inputs": validated,
            "measured_elapsed_ms": measured_elapsed_ms,
            "fixed_candidate": fixed_candidate,
            "fixed_comparison_to_baseline": fixed_comparison,
            "observed_response": response,
            "result": result,
        }
        completed_cases.append(case_payload)
        _write_json(cases_dir / f"{definition.case_id}.json", case_payload)
        print(
            f"[{case_number:02d}/{len(definitions):02d}] {definition.case_id}: "
            f"{result.get('status')} / {len(result.get('candidates', []))} returned / "
            f"{measured_elapsed_ms:.1f} ms"
        )

    assert baseline_result is not None
    single_input_cases = [
        case for case in completed_cases if case["case"]["kind"] == "single_input"
    ]
    bugs = [
        case["case"]["case_id"]
        for case in single_input_cases
        if case["observed_response"]["possible_parameter_or_state_bug"]
    ]
    ranking_unchanged = [
        case["case"]["case_id"]
        for case in single_input_cases
        if not case["observed_response"]["ranking_changed"]
    ]

    manifest = {
        "schema_version": "1.0",
        "audit": "round7-task-response",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git": {
            "branch": _git_value("branch", "--show-current"),
            "head": _git_value("rev-parse", "HEAD"),
            "status": _git_value("status", "--short"),
        },
        "profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "hash": profile_hash,
            "seed": profile.optimizer.seed,
            "method": profile.optimizer.method,
            "evaluation_budget": (
                profile.optimizer.iterations * profile.optimizer.evaluations_per_iteration
            ),
        },
        "rules": {
            "no_seed_changes": True,
            "no_coefficient_changes": True,
            "no_bound_expansion": True,
            "no_mission_to_geometry_rules": True,
            "fixed_candidate_layer": "same baseline design and sizing; mission inputs only",
            "full_search_layer": "same profile, algorithm and seed; mission inputs changed per case",
        },
        "case_ids": [case["case"]["case_id"] for case in completed_cases],
    }
    summary = {
        "schema_version": "1.0",
        "case_count": len(completed_cases),
        "preset_baseline_count": sum(
            case["case"]["kind"] == "preset_baseline" for case in completed_cases
        ),
        "single_input_count": len(single_input_cases),
        "structured_statuses": {
            status: sum(case["result"].get("status") == status for case in completed_cases)
            for status in sorted({str(case["result"].get("status")) for case in completed_cases})
        },
        "possible_parameter_or_state_bugs": bugs,
        "ranking_unchanged_cases": ranking_unchanged,
        "constraint_inactive_ranking_unchanged_cases": [
            case["case"]["case_id"]
            for case in single_input_cases
            if case["observed_response"]["ranking_unchanged_reason"]
            == "changed_constraint_not_activated_for_fixed_candidate_and_top_k_stable"
        ],
        "model_response_ranking_unchanged_cases": [
            case["case"]["case_id"]
            for case in single_input_cases
            if case["observed_response"]["ranking_unchanged_reason"]
            == "model_response_changed_but_top_k_order_stable"
        ],
        "all_fixed_candidate_geometry_unchanged": all(
            case["fixed_comparison_to_baseline"]["same_design"]
            and case["fixed_comparison_to_baseline"]["same_geometry_state"]
            and case["fixed_comparison_to_baseline"]["same_geometry_fingerprint"]
            for case in single_input_cases
        ),
        "design_hash_changed_without_geometry_change_cases": [
            case["case"]["case_id"]
            for case in single_input_cases
            if case["fixed_comparison_to_baseline"]["same_geometry_fingerprint"]
            and not case["fixed_comparison_to_baseline"]["same_design_hash"]
        ],
        "unconnected_existing_inputs": [
            case["case"]["case_id"]
            for case in single_input_cases
            if case["observed_response"]["observed_categories"]
            == ["input_recorded_but_no_observed_downstream_effect"]
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "summary.json", summary)

    case_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    evaluation_rows: list[dict[str, object]] = []
    fixed_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []
    for case in completed_cases:
        result = case["result"]
        selection = result.get("selection", {})
        case_rows.append(
            {
                "case_id": case["case"]["case_id"],
                "label": case["case"]["label"],
                "kind": case["case"]["kind"],
                "preset_id": case["case"]["preset_id"],
                "changed_inputs_json": _json_text(case["case"]["changed_inputs"]),
                "inputs_json": _json_text(case["inputs"]),
                "seed": result.get("search", {}).get("seed"),
                "profile_id": result.get("profile", {}).get("id"),
                "profile_version": result.get("profile", {}).get("version"),
                "profile_hash": result.get("profile", {}).get("hash"),
                "result_status": result.get("status"),
                "evaluations": result.get("search", {}).get("evaluations"),
                "valid_evaluations": result.get("search", {}).get("valid"),
                "invalid_evaluations": result.get("search", {}).get("invalid"),
                "search_elapsed_ms": result.get("search", {}).get("elapsed_ms"),
                "measured_elapsed_ms": case["measured_elapsed_ms"],
                "requested_candidates": selection.get("requested_count"),
                "returned_candidates": selection.get(
                    "returned_count", len(result.get("candidates", []))
                ),
                "feasible_candidates": selection.get("feasible_valid_count"),
                "selection_outcome": selection.get("outcome"),
                "ranking_changed": (
                    case["observed_response"].get("ranking_changed")
                    if case["observed_response"]
                    else ""
                ),
            }
        )
        candidate_rows.extend(
            _candidate_row(case, candidate) for candidate in result.get("candidates", [])
        )
        evaluation_rows.extend(
            _evaluation_row(case, record)
            for record in result.get("search", {}).get("records", [])
            if isinstance(record, dict)
        )
        if case["fixed_comparison_to_baseline"]:
            comparison = case["fixed_comparison_to_baseline"]
            fixed_rows.append(
                {
                    "case_id": case["case"]["case_id"],
                    "changed_inputs_json": _json_text(comparison["changed_inputs"]),
                    "same_design": comparison["same_design"],
                    "same_sizing": comparison["same_sizing"],
                    "same_geometry_state": comparison["same_geometry_state"],
                    "same_geometry_fingerprint": comparison["same_geometry_fingerprint"],
                    "same_design_hash": comparison["same_design_hash"],
                    "changed_condition_keys": ";".join(comparison["changed_condition_keys"]),
                    "changed_metric_keys": ";".join(comparison["changed_metric_keys"]),
                    "constraint_changes_json": _json_text(comparison["constraint_changes"]),
                    "objective_before": comparison["objective_before"],
                    "objective_after": comparison["objective_after"],
                    "objective_changed": comparison["objective_changed"],
                    "feasible_before": comparison["feasible_before"],
                    "feasible_after": comparison["feasible_after"],
                }
            )
        if case["observed_response"]:
            response = case["observed_response"]
            classification_rows.append(
                {
                    "case_id": case["case"]["case_id"],
                    "expected_mechanisms": ";".join(response["expected_mechanisms"]),
                    "observed_categories": ";".join(response["observed_categories"]),
                    "input_forwarded": response["input_forwarded"],
                    "candidate_pool_changed": response["candidate_pool_changed"],
                    "top_k_changed": response["top_k_changed"],
                    "ranking_changed": response["ranking_changed"],
                    "inactive_fixed_candidate_constraints": ";".join(
                        response["inactive_fixed_candidate_constraints"]
                    ),
                    "ranking_unchanged_reason": response["ranking_unchanged_reason"] or "",
                    "missing_expected_mechanisms": ";".join(
                        response["missing_expected_mechanisms"]
                    ),
                    "possible_parameter_or_state_bug": response["possible_parameter_or_state_bug"],
                    "interpretation": response["interpretation"],
                }
            )

    _write_csv(output_dir / "cases.csv", case_rows, list(case_rows[0]))
    _write_csv(output_dir / "top_candidates.csv", candidate_rows, list(candidate_rows[0]))
    _write_csv(output_dir / "evaluations.csv", evaluation_rows, list(evaluation_rows[0]))
    _write_csv(output_dir / "fixed_candidate_comparison.csv", fixed_rows, list(fixed_rows[0]))
    _write_csv(
        output_dir / "input_response_classification.csv",
        classification_rows,
        list(classification_rows[0]),
    )

    print(f"Completed. Raw JSON/CSV: {output_dir}")
    print(f"Possible parameter/state bugs: {bugs or 'none'}")
    print(f"Ranking unchanged for: {ranking_unchanged or 'none'}")
    return 1 if bugs else 0


if __name__ == "__main__":
    raise SystemExit(main())

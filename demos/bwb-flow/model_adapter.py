"""Explicit, coefficient-only adapter to externally supplied MIT/nTop resources.

No upstream source, training data or weights are copied. Inference runs in a
short-lived child so the upstream sys.path/module globals cannot alter the demo.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ADAPTER_VERSION = "mit-coefficients-v1"
MIT_COMMIT = "b516d4b3e2e5e34fbd5233eacdf15317a96dc2d9"
DECODER_ID = "mit_ntop_ratio_v1"
GEOMETRY_KEYS = ("B1/C1", "B2/C1", "B3/C1", "C2/C1", "C3/C1", "C4/C1", "S1", "S3", "X3/C1", "C1")
QUANTITIES = ("CL", "CD", "LD", "Re_L", "M_inf")
MISSING = {"L_N": "coefficient_reference_provenance_unresolved", "D_N": "coefficient_reference_provenance_unresolved", "Cm": "not_provided_by_wrapper", "control_response": "not_provided_by_wrapper", "distributed_loads": "not_provided_by_wrapper", "stress": "no_structural_response_model_connected"}
# SHA256 over UTF-8 text with universal-newline normalization; portable checkout.
AUDITED_SHA256 = {
    "predict_ld.py": "149252ffee028823c7a1b610643d72a5ee36966d5e62f3a220d7ffc69e74488e",
    "flight_conversion.py": "f2a33c85a884b3b1b4e5c74e4f1a25f5150b74ecc2eaa0d87f3dc0627656dc2d",
    "regressor.py": "a2e1f504a9dbf31f8e1dcffabf67887611f4260ab6528abf4bb91e027d24bebf",
    "aero_design_space.json": "5b9db166b15c439ceeaf2e49d6f0c14140706d23ddfdf624c919c019d80cd1a8",
    "reg_full.json": "3eac7742b4cedc3fd0d0d0e7912d8986ad19ee3281d56c2b3010a9223ae69206",
}
SAMPLE_REQUEST = {
    "geometry_decoder_id": DECODER_ID,
    "geometry": {"B1/C1": .15, "B2/C1": .12, "B3/C1": .52, "C2/C1": .70, "C3/C1": .23, "C4/C1": .075, "S1": 50., "S3": 30., "X3/C1": .575, "C1": 3000.},
    "condition": {"alt_kft": 15., "kcas": 180., "aoa": 6.},
}
MIT_EXAMPLE = SAMPLE_REQUEST
_SCHEMA_BOX = {"B1/C1": [.1000261, .1999978], "B2/C1": [.0500143, .1999828], "B3/C1": [.3500802, .6999412], "C2/C1": [.5500737, .8499953], "C3/C1": [.1800016, .2799979], "C4/C1": [.0600129, .0899936], "S1": [40.003, 59.9993], "S3": [20.0015, 44.9884], "X3/C1": [.5, .6499], "C1": [2500., 4000.]}
MIT_INPUT_SCHEMA = {
    "geometry": {k: {"label": k, "unit": "mm" if k == "C1" else "deg" if k in ("S1", "S3") else "dimensionless", "min": limits[0], "max": limits[1], "step": 10 if k == "C1" else .1 if k in ("S1", "S3") else .001} for k, limits in _SCHEMA_BOX.items()},
    "condition": {
        "alt_kft": {"label": "高度", "unit": "kft", "min": .0015, "max": 18., "step": .1},
        "kcas": {"label": "校准空速", "unit": "knots CAS", "min": 33.02, "max": 249.95, "step": 1.},
        "aoa": {"label": "攻角", "unit": "deg", "min": -8., "max": 16., "step": .1},
    },
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def resolve_mit_root(root=None):
    """Explicit server argument > BWB_MIT_ROOT > known sibling resource folder."""
    selected = root if root is not None else os.environ.get("BWB_MIT_ROOT")
    return Path(selected).expanduser().resolve() if selected else Path(__file__).resolve().parents[3] / "MIT" / "official_hackathon"


def _resource_info(root):
    folder = resolve_mit_root(root) / "models" / "ld_surrogate"
    hashes, missing, altered = {}, [], []
    for name, expected in AUDITED_SHA256.items():
        try:
            hashes[name] = hashlib.sha256((folder / name).read_text(encoding="utf-8").encode()).hexdigest()
            if hashes[name] != expected:
                altered.append(name)
        except (OSError, UnicodeError):
            missing.append(name)
    failure = "external_resources_missing" if missing else "source_version_not_audited" if altered else None
    return folder, hashes, failure, missing, altered


def model_catalog(root=None):
    folder, hashes, failure, missing, altered = _resource_info(root)
    bounds = None
    if not failure:
        # The controlled schema contains the audited resource bounds converted
        # to native units. Both presentation and enforcement use these exact
        # numbers (avoids a one-ULP rejection at an advertised box endpoint).
        bounds = {k: [v["min"], v["max"]] for k, v in MIT_INPUT_SCHEMA["geometry"].items()}
    return [{
        "id": "mit_ld_full", "version": ADAPTER_VERSION,
        "source_commit": MIT_COMMIT if not failure else None,
        "expected_source_commit": MIT_COMMIT, "source_artifact_sha256": hashes,
        "geometry_decoder_id": DECODER_ID,
        "units": {**{k: "dimensionless" for k in GEOMETRY_KEYS}, "C1": "mm", "S1": "deg", "S3": "deg", "alt_kft": "kft", "kcas": "knots CAS", "aoa": "deg", **{k: "dimensionless" for k in QUANTITIES}},
        "axes": {"CL_CD": "native integrated lift/drag coefficients", "body_axis_transform": None, "reason": "wrapper exports no force vector or axis transform"},
        "S_ref": None, "length_ref": None, "moment_reference": None,
        "reference_status": "paper_canonical_reference_known_but_wrapper_label_provenance_unresolved",
        "paper_reference_only": {"S_ref_m2": 1., "length_ref_m": 1., "moment_reference": "nose", "usable_for_force_conversion": False, "evidence_id": "MIT-PAPER-REF"},
        "supported_inputs": ["geometry_decoder_id", "geometry", "condition"],
        "supported_quantities": list(QUANTITIES), "supported_load_cases": ["single_steady_aerodynamic_coefficient_condition"],
        "unsupported_quantities": dict(MISSING),
        "validity_domain": {"geometry_box": bounds, "geometry_box_source": "aero_design_space.json feasible-subset SEARCH box; C1 from README", "raw_flight_box": {k: [v["min"], v["max"]] for k, v in MIT_INPUT_SCHEMA["condition"].items()}, "converted_flight_box": {"Re_L": [5.07e4, 1.e8], "M_inf": [.05, .5]}, "joint_coverage": "unknown; axis-aligned box does not establish joint training support"},
        "domain_check_status": "per_prediction_required", "evidence_ids": ["MIT-WRAPPER", "MIT-DOMAIN", "MIT-PAPER-REF", "MIT-LABEL-GAP"],
        "resource_available": failure is None, "failure_reason": failure,
        "resource_diagnostics": {"missing": missing, "changed_since_audit": altered},
        "analysis_modes": {"coefficient_analysis": failure is None, "aircraft_trim_mission": False},
        "uncertainty_metadata": None, "uncertainty_reason": "no_independent_calibration_or_test_data_and_pretraining_membership_unknown",
        "sample_request": json.loads(json.dumps(SAMPLE_REQUEST)),
    }]


def supports_analysis(metadata, required, geometry_decoder_id=None):
    """Capability check, never a domain or engineering-validation certificate."""
    missing = sorted(set(required) - set(metadata.get("supported_quantities", [])))
    reasons = ["missing_quantity:" + q for q in missing]
    if metadata.get("resource_available") is False:
        reasons.append(metadata.get("failure_reason") or "model_unavailable")
    if geometry_decoder_id is not None and geometry_decoder_id != metadata.get("geometry_decoder_id"):
        reasons.append("geometry_decoder_mismatch")
    return {"supported": not reasons, "missing_quantities": missing, "reasons": reasons}


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("finite_number_required:" + name)
    return float(value)


_WORKER = r'''
import json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import predict_ld as wrapper
p = json.load(sys.stdin)
c, g = p["condition"], p["geometry"]
fs = wrapper.FC.convert(c["alt_kft"], c["kcas"], c["aoa"], g["C1"])
warnings = wrapper.FC.check_ranges(fs)
if warnings:
    print(json.dumps({"failure_reason": "flight_out_of_domain", "warnings": warnings, "converted_condition": {"Re_L": fs.Re_L, "M_inf": fs.M_inf}}))
else:
    print(json.dumps({"result": wrapper.predict_ld(g, **c)}, allow_nan=False))
'''


def predict_mit(payload, root=None):
    """Return JSON-compatible {model, prediction}; failed quantities stay absent."""
    metadata = model_catalog(root)[0]
    prediction = {
        "condition_id": None, "state_id": None, "quantities": {},
        "availability_per_quantity": {q: {"available": False, "reason": "not_evaluated"} for q in QUANTITIES},
        "failure_reason": None, "status": "not_evaluated", "domain_check_status": "not_checked",
        "uncertainty_metadata": None, "uncertainty_reason": metadata["uncertainty_reason"],
        "evidence_ids": metadata["evidence_ids"],
    }
    prediction["availability_per_quantity"].update({q: {"available": False, "reason": reason} for q, reason in MISSING.items()})
    def fail(reason, details=None):
        prediction.update(status="unavailable", failure_reason=reason)
        if details is not None:
            prediction["diagnostics"] = details
        for q in QUANTITIES:
            prediction["availability_per_quantity"][q] = {"available": False, "reason": reason}
        return {"model": metadata, "prediction": prediction}
    if not isinstance(payload, dict):
        return fail("input_object_required")
    allowed = {"geometry_decoder_id", "geometry", "condition", "condition_id", "state_id"}
    if set(payload) - allowed:
        return fail("unknown_input_fields", sorted(set(payload) - allowed))
    if payload.get("geometry_decoder_id") != DECODER_ID:
        return fail("geometry_decoder_mismatch")
    try:
        for name, keys in (("geometry", GEOMETRY_KEYS), ("condition", ("alt_kft", "kcas", "aoa"))):
            values = payload.get(name)
            if not isinstance(values, dict) or set(values) != set(keys):
                return fail("native_keys_required:" + name, {"required": list(keys)})
            for key in keys:
                _finite_number(values[key], name + "." + key)
        for key in ("state_id", "condition_id"):
            if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
                return fail("nonempty_string_required:" + key)
        prediction["state_id"] = payload.get("state_id", _hash({"decoder": DECODER_ID, "geometry": payload["geometry"]}))
        prediction["condition_id"] = payload.get("condition_id", _hash(payload["condition"]))
        prediction["input_hash"] = _hash({"geometry": payload["geometry"], "condition": payload["condition"], "model": metadata["source_artifact_sha256"]})
    except ValueError as exc:
        return fail(str(exc))
    if metadata["failure_reason"]:
        return fail(metadata["failure_reason"], metadata["resource_diagnostics"])
    violations = []
    for group, box in (("geometry", metadata["validity_domain"]["geometry_box"]), ("condition", metadata["validity_domain"]["raw_flight_box"])):
        for key, (lo, hi) in box.items():
            value = payload[group][key]
            if not lo <= value <= hi:
                violations.append({"input": key, "value": value, "bounds": [lo, hi]})
    if violations:
        prediction["domain_check_status"] = "outside_declared_box"
        return fail("input_out_of_domain", violations)
    try:
        proc = subprocess.run([sys.executable, "-B", "-c", _WORKER, str(resolve_mit_root(root) / "models" / "ld_surrogate")], input=json.dumps(payload, allow_nan=False), text=True, capture_output=True, timeout=30, check=False)
        if proc.returncode:
            return fail("upstream_inference_failed", {"exit_code": proc.returncode, "message": proc.stderr[-1500:]})
        response = json.loads(proc.stdout)
        if response.get("failure_reason"):
            prediction["domain_check_status"] = "outside_converted_flight_box"
            return fail(response["failure_reason"], response)
        result = response["result"]
        for q in QUANTITIES:
            _finite_number(result[q], q)
        if result["CD"] <= 0:
            return fail("nonpositive_CD")
        if result["warnings"]:
            return fail("upstream_domain_warning", result["warnings"])
        prediction.update(status="coefficient_prediction", quantities={q: result[q] for q in QUANTITIES}, domain_check_status="inside_declared_boxes_joint_support_unknown", condition=payload["condition"], geometry=payload["geometry"])
        prediction["availability_per_quantity"].update({q: {"available": True, "reason": None} for q in QUANTITIES})
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        return fail("inference_boundary_error", str(exc))
    return {"model": metadata, "prediction": prediction}

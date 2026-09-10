"""Adapter regressions and synthetic metric arithmetic, NOT physical validation."""
import copy
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from model_adapter import (DECODER_ID, MIT_EXAMPLE, MIT_INPUT_SCHEMA, model_catalog, predict_mit,
                           resolve_mit_root, supports_analysis)
from uq_evaluate import EvaluationError, SCHEMA_VERSION, evaluate


def synthetic_fixture():
    """Small hand-calculable numbers, never published as an empirical dataset."""
    ident = lambda i: {"sample_id": i, "group_id": "group-" + i}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset": {"id": "SYNTHETIC-ARITHMETIC-ONLY", "version": "1", "reference_fidelity": "synthetic_test_numbers"},
        "model": {"id": "synthetic", "version": "1", "training_provenance": {"status": "known", "complete_exposure_list": True, "evidence_id": "unit-test-fixture-only", "seen_samples": [ident("train"), ident("validation")]}},
        "splits": {"proper_train": [ident("train")], "validation": [ident("validation")], "calibration": [ident("calibration")], "test": [ident("a"), ident("b"), ident("c")]},
        "protection": {"splits_frozen_before_fitting": True, "calibration_not_used_for_tuning_or_preprocessing": True, "test_not_used_for_tuning_calibration_or_selection": True, "evidence_id": "unit-test-fixture-only"},
    }
    reference = [{**ident(sid), "domain_group": domain, "optimization_selected": selected, "quantities": {"q": value}, "units": {"q": "synthetic_unit"}} for sid, domain, selected, value in (("a", "in_domain", False, 1.), ("b", "boundary", True, 3.), ("c", "out_of_domain", False, 6.))]
    predictions = {"metadata": {"model_id": "synthetic", "model_version": "1", "dataset_id": "SYNTHETIC-ARITHMETIC-ONLY", "dataset_version": "1", "reference_fidelity": "synthetic_test_numbers", "prediction_run_id": "fixture", "predictions_frozen_before_test_labels_evidence_id": "unit-test-fixture-only", "intervals": {"type": "prediction_interval", "nominal_level": .8, "distribution_statement": "synthetic arithmetic only; no coverage claim", "calibration": {"method": "fixture", "sample_count": 1, "data_version": "1", "evidence_id": "unit-test-fixture-only"}}}, "rows": [{**ident(sid), "quantities": {"q": {"mean": mean, "lower": lower, "upper": upper}}} for sid, mean, lower, upper in (("a", 2., .5, 2.5), ("b", 3., 2., 4.), ("c", 4., 3., 5.))]}
    return manifest, reference, predictions


class CapabilityTests(unittest.TestCase):
    def test_missing_trim_and_decoder_are_explicit(self):
        metadata = model_catalog()[0]
        check = supports_analysis(metadata, ["CL", "CD", "Cm", "control_response", "distributed_loads"], "demo_three_trapezoids")
        self.assertFalse(check["supported"])
        self.assertEqual(check["missing_quantities"], ["Cm", "control_response", "distributed_loads"])
        self.assertIn("geometry_decoder_mismatch", check["reasons"])
        self.assertIsNone(metadata["S_ref"])
        self.assertIsNone(metadata["moment_reference"])

    def test_reject_nonobjects_unknown_fields_native_keys_and_nonfinite(self):
        for value in ([], 0, "", False, None):
            self.assertEqual(predict_mit(value)["prediction"]["failure_reason"], "input_object_required")
        bad = copy.deepcopy(MIT_EXAMPLE)
        bad["geometry"]["span_m"] = 8
        self.assertIn("native_keys_required", predict_mit(bad)["prediction"]["failure_reason"])
        for value in (float("nan"), float("inf"), True, "3000"):
            bad = copy.deepcopy(MIT_EXAMPLE)
            bad["geometry"]["C1"] = value
            self.assertIn("finite_number_required", predict_mit(bad)["prediction"]["failure_reason"])
        bad = copy.deepcopy(MIT_EXAMPLE)
        bad["geometry_decoder_id"] = "demo_three_trapezoids"
        self.assertEqual(predict_mit(bad)["prediction"]["failure_reason"], "geometry_decoder_mismatch")

    def test_missing_external_resource_remains_unavailable(self):
        result = predict_mit(MIT_EXAMPLE, root=resolve_mit_root() / "nonexistent-fixture")
        self.assertEqual(result["prediction"]["failure_reason"], "external_resources_missing")
        self.assertEqual(result["prediction"]["quantities"], {})


@unittest.skipUnless(model_catalog()[0]["resource_available"], "Audited external MIT files unavailable: actual inference NOT executed")
class RealMITAdapterTests(unittest.TestCase):
    def test_advertised_domain_endpoints_match_enforced_numbers(self):
        domain = model_catalog()[0]["validity_domain"]
        for group, box in (("geometry", "geometry_box"), ("condition", "raw_flight_box")):
            for key, field in MIT_INPUT_SCHEMA[group].items():
                self.assertEqual([field["min"], field["max"]], domain[box][key])

    def test_actual_inference_sample_and_capabilities(self):
        result = predict_mit(MIT_EXAMPLE)
        prediction = result["prediction"]
        self.assertEqual(prediction["status"], "coefficient_prediction", prediction)
        self.assertAlmostEqual(prediction["quantities"]["CL"], .203178284678, places=9)
        self.assertAlmostEqual(prediction["quantities"]["CD"], .01665231632, places=9)
        self.assertAlmostEqual(prediction["quantities"]["LD"], 12.20120256976, places=8)
        self.assertTrue(supports_analysis(result["model"], ["CL", "CD"], DECODER_ID)["supported"])
        self.assertFalse(prediction["availability_per_quantity"]["L_N"]["available"])
        self.assertIsNone(prediction["uncertainty_metadata"])
        self.assertTrue(prediction["state_id"] and prediction["condition_id"])

    def test_geometry_and_raw_flight_domain_before_call(self):
        for group, key, value in (("geometry", "S3", 60.), ("geometry", "C1", 1000.), ("condition", "alt_kft", 40.), ("condition", "aoa", 20.)):
            bad = copy.deepcopy(MIT_EXAMPLE)
            bad[group][key] = value
            with patch("model_adapter.subprocess.run") as run:
                self.assertEqual(predict_mit(bad)["prediction"]["failure_reason"], "input_out_of_domain")
                run.assert_not_called()

    def test_converted_mach_domain_actual_converter(self):
        bad = copy.deepcopy(MIT_EXAMPLE)
        bad["condition"].update(alt_kft=18., kcas=249.)
        result = predict_mit(bad)["prediction"]
        self.assertEqual(result["failure_reason"], "flight_out_of_domain")
        self.assertGreater(result["diagnostics"]["converted_condition"]["M_inf"], .5)

    def test_nonpositive_cd_and_nonfinite_upstream_results_rejected(self):
        raw = {"CL": .2, "CD": -.01, "LD": -20., "Re_L": 1.e6, "M_inf": .2, "warnings": []}
        with patch("model_adapter.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"result": raw}), stderr="")):
            self.assertEqual(predict_mit(MIT_EXAMPLE)["prediction"]["failure_reason"], "nonpositive_CD")
        raw["CD"] = float("nan")
        with patch("model_adapter.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"result": raw}), stderr="")):
            self.assertEqual(predict_mit(MIT_EXAMPLE)["prediction"]["quantities"], {})


class OfflineUQTests(unittest.TestCase):
    def test_no_data_is_not_evaluated(self):
        result = evaluate()
        self.assertEqual(result["status"], "not_evaluated")
        self.assertIsNone(result["metrics"])

    def test_synthetic_metrics_arithmetic_and_groups(self):
        result = evaluate(*synthetic_fixture())
        metric = result["metrics"]["q"]
        self.assertEqual(metric["unit"], "synthetic_unit")
        self.assertAlmostEqual(metric["overall"]["mae"], 1.)
        self.assertAlmostEqual(metric["overall"]["rmse"], math.sqrt(5 / 3))
        self.assertAlmostEqual(metric["overall"]["coverage"], 2 / 3)
        self.assertAlmostEqual(metric["overall"]["mean_interval_width"], 2.)
        self.assertAlmostEqual(metric["overall"]["interval_score"], 16 / 3)
        self.assertEqual(metric["by_selection"]["optimization_selected"]["n"], 1)
        self.assertEqual(metric["selected_by_domain"]["boundary"]["n"], 1)
        self.assertIsNone(metric["by_domain"]["unknown"]["coverage"])

    def test_point_errors_do_not_create_intervals(self):
        manifest, ref, pred = synthetic_fixture()
        pred["metadata"]["intervals"] = None
        for row in pred["rows"]:
            row["quantities"]["q"] = {"mean": row["quantities"]["q"]["mean"]}
        result = evaluate(manifest, ref, pred)
        self.assertIsNone(result["metrics"]["q"]["overall"]["coverage"])
        self.assertIsNone(result["uncertainty_metadata"])

    def test_unknown_pretraining_and_protected_set_declarations_rejected(self):
        manifest, ref, pred = synthetic_fixture()
        manifest["model"]["training_provenance"]["status"] = "unknown"
        with self.assertRaisesRegex(EvaluationError, "unknown_training_provenance"):
            evaluate(manifest, ref, pred)
        manifest, ref, pred = synthetic_fixture()
        manifest["protection"]["calibration_not_used_for_tuning_or_preprocessing"] = False
        with self.assertRaisesRegex(EvaluationError, "protected_set_declaration"):
            evaluate(manifest, ref, pred)

    def test_sample_group_and_pretrained_overlap_rejected(self):
        for mode in ("sample", "group", "pretrained"):
            manifest, ref, pred = synthetic_fixture()
            if mode == "sample":
                manifest["splits"]["calibration"] = [manifest["splits"]["test"][0]]
            elif mode == "group":
                manifest["splits"]["calibration"][0]["group_id"] = "group-a"
            else:
                manifest["model"]["training_provenance"]["seen_samples"].append({"sample_id": "other-row-same-shape", "group_id": "group-a"})
            with self.assertRaises(EvaluationError):
                evaluate(manifest, ref, pred)

    def test_provenance_units_fidelity_and_complete_test_enforced(self):
        for mode in ("units", "fidelity", "partial", "group"):
            manifest, ref, pred = synthetic_fixture()
            if mode == "units":
                ref[1]["units"]["q"] = "other_unit"
            elif mode == "fidelity":
                pred["metadata"]["reference_fidelity"] = "different_reference"
            elif mode == "partial":
                pred["rows"].pop()
            else:
                pred["rows"][0]["group_id"] = "not-a"
            with self.assertRaises(EvaluationError):
                evaluate(manifest, ref, pred)

    def test_nonfinite_reversed_intervals_and_count_mismatch_rejected(self):
        for mode in ("nan", "reversed", "count", "nominal"):
            manifest, ref, pred = synthetic_fixture()
            if mode == "nan":
                pred["rows"][0]["quantities"]["q"]["mean"] = float("nan")
            elif mode == "reversed":
                pred["rows"][0]["quantities"]["q"]["lower"] = 10
            elif mode == "count":
                pred["metadata"]["intervals"]["calibration"]["sample_count"] = 7
            else:
                pred["metadata"]["intervals"]["nominal_level"] = 1
            with self.assertRaises(EvaluationError):
                evaluate(manifest, ref, pred)


if __name__ == "__main__":
    unittest.main()

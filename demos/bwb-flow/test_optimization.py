"""Search behavior tests plus a small real evaluator repeatability check.

Synthetic landscapes below test selection/bookkeeping, not aircraft physics.
The two real searches verify numerical reproducibility under the same low-order
model; neither is an independent aerodynamic or structural validation.
"""
from copy import deepcopy
import math
import unittest

from configuration import DEFAULTS
from optimization import digest, optimize, validate_search


SMALL_SEARCH = {"variables": {"span_m": [7., 8.], "thickness_mm": [.8, 1.2]},
                "grid_levels": 2, "search_budget": 2, "max_rounds": 1}
MISSION_KEYS = ("payload_kg", "cruise_km", "cruise_speed_ms", "altitude_m")


class SyntheticEvaluator:
    """Explicit test fixture with mass cost and optional span feasibility gate."""
    def __init__(self, mode="feasible"):
        self.mode = mode
        self.calls = []

    def __call__(self, candidate, model_config=None, solver_config=None):
        inputs = deepcopy(candidate)
        configuration = {"model": deepcopy(model_config), "solver": deepcopy(solver_config)}
        self.calls.append({"inputs": inputs, "configuration": configuration})
        margin = inputs["span_m"] - 8. if self.mode == "span_gate" else -1. if self.mode == "infeasible" else 1.
        state = "unknown" if self.mode == "unknown" else "feasible" if margin >= 0 else "infeasible"
        mass = 100. + inputs["span_m"] + inputs["thickness_mm"]
        identity = digest({"inputs": inputs, "configuration": configuration, "fixture": self.mode})
        return {
            "inputs": inputs, "design": {k: inputs[k] for k in ("span_m", "thickness_mm", "root_chord_m", "power_kw")},
            "requirements": {k: inputs[k] for k in MISSION_KEYS},
            "load_case_definition": {"load_factor": inputs["load_factor"], "fixture": True},
            "analysis_id": "synthetic-" + identity, "analysis_hash": identity,
            "model_metadata": {"id": "SYNTHETIC-SELECTION-TEST-ONLY"}, "configuration": configuration,
            "status": "unsupported" if state == "unknown" else "demo_converged",
            "evaluation_status": state, "demo_constraints_satisfied": state == "feasible",
            # Retaining partial mass deliberately checks that unknown states do
            # not acquire a pretend usable objective just because a number exists.
            "mass": {"mass_kg": mass}, "fuel_loaded_kg": mass / 10.,
            "constraints": [{"id": "synthetic_span", "normalized_margin": margin, "value": inputs["span_m"], "limit": 8., "unit": "m", "g": -margin, "pass_": margin >= 0}],
            "failure": "synthetic_unavailable_model" if state == "unknown" else None,
        }


class SearchBehaviorTests(unittest.TestCase):
    def test_json_integer_inputs_do_not_duplicate_candidates(self):
        numeric_inputs = {k: int(v) if float(v).is_integer() else v for k, v in DEFAULTS.items()}
        a = optimize(search=SMALL_SEARCH, evaluator=SyntheticEvaluator())
        b = optimize(inputs=numeric_inputs, search=SMALL_SEARCH, evaluator=SyntheticEvaluator())
        self.assertEqual([x['analysis_hash'] for x in a['candidates']], [x['analysis_hash'] for x in b['candidates']])
        self.assertEqual(a['run_id'], b['run_id'])

    def test_only_supported_hardware_variables_and_finite_bounds(self):
        bad = [
            {"variables": {"payload_kg": [50., 100.], "span_m": [7., 8.]}},
            {"variables": {"cruise_km": [400., 600.], "thickness_mm": [.8, 1.2]}},
            {"variables": {"span_m": [7., 8.]}},
            {"variables": {"span_m": [7., float("nan")], "thickness_mm": [.8, 1.2]}},
            {"variables": {"span_m": [7., 8.], "thickness_mm": [.8, 1.2], "root_chord_m": [3., 4.], "power_kw": [50., 80.]}},
            {"objective": "invented_efficiency"}, {"search_budget": True},
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_search(item)

    def test_problem_inputs_and_configuration_are_frozen_during_search(self):
        supplied = {"payload_kg": 60., "cruise_km": 450.}
        model = {"cd0": .031}
        solver = {"mission_steps": 18}
        settings = deepcopy(SMALL_SEARCH)
        evaluator = SyntheticEvaluator()
        def mutate_caller_objects(record, result):
            supplied["payload_kg"] = 150.
            model["cd0"] = .07
            solver["mission_steps"] = 72
            settings["variables"]["span_m"][0] = 6.
        report = optimize(supplied, model, solver, settings, evaluator, mutate_caller_objects)
        for call in evaluator.calls:
            self.assertEqual(call["inputs"]["payload_kg"], 60.)
            self.assertEqual(call["inputs"]["cruise_km"], 450.)
            self.assertEqual(call["inputs"]["rated_payload_kg"], DEFAULTS["rated_payload_kg"])
            self.assertEqual(call["configuration"], {"model": {"cd0": .031}, "solver": {"mission_steps": 18}})
        self.assertEqual(report["problem"]["mission"]["payload_kg"], 60.)
        self.assertEqual(report["problem"]["variables"]["span_m"], [7., 8.])
        self.assertEqual(report["seed"]["M03"], "skipped")

    def test_cache_budget_and_grid_account_for_unique_evaluations(self):
        evaluator = SyntheticEvaluator()
        report = optimize(search=SMALL_SEARCH, evaluator=evaluator)
        hashes = [digest(call["inputs"]) for call in evaluator.calls]
        self.assertEqual(len(hashes), len(set(hashes)))
        self.assertEqual(report["grid_reference"]["points"], 4)
        # Baseline is a grid corner and must be reused, not charged twice.
        self.assertEqual(report["grid_reference"]["evaluations"], 3)
        self.assertEqual(report["search"]["evaluations"], 2)
        self.assertEqual(report["search"]["total_evaluations"], 6)
        self.assertEqual(len(report["candidates"]), len(evaluator.calls))
        self.assertEqual(report["search"]["stop_reason"], "evaluation_budget_exhausted")

    def test_unknown_is_never_given_objective_or_selected(self):
        report = optimize(search=SMALL_SEARCH, evaluator=SyntheticEvaluator("unknown"))
        self.assertEqual(report["status"], "no_feasible_candidate")
        self.assertIsNone(report["best"])
        self.assertTrue(all(r["objective"] is None and r["evaluation_status"] == "unknown" for r in report["candidates"]))
        self.assertIn("not a proof", report["selection"]["reason"])

    def test_valid_infeasible_objectives_retained_but_not_selected(self):
        report = optimize(search=SMALL_SEARCH, evaluator=SyntheticEvaluator("span_gate"))
        infeasible = [r for r in report["candidates"] if r["evaluation_status"] == "infeasible"]
        self.assertTrue(infeasible)
        self.assertTrue(all(math.isfinite(r["objective"]) for r in infeasible))
        self.assertEqual(report["best"]["evaluation_status"], "feasible")
        self.assertGreaterEqual(report["best"]["inputs"]["span_m"], 8.)
        self.assertLess(min(r["objective"] for r in infeasible), report["best"]["mass"]["mass_kg"])
        self.assertEqual(report["best"]["mass"]["mass_kg"], 100. + 8. + .8)

    def test_no_feasible_report_preserves_real_infeasible_values(self):
        report = optimize(search=SMALL_SEARCH, evaluator=SyntheticEvaluator("infeasible"))
        self.assertIsNone(report["best"])
        self.assertIsNone(report["grid_reference"]["best"])
        self.assertTrue(all(r["evaluation_status"] == "infeasible" and r["objective"] is not None for r in report["candidates"]))
        self.assertEqual(report["selection"]["global_optimality"], "not_proven")
        self.assertEqual(report["independent_review"]["status"], "not_performed")


class ActualSmallSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluations = []
        numerics = {"fuel_scan_points": 31, "mission_steps": 12}
        cls.first = optimize(solver_config=numerics, search=SMALL_SEARCH,
                             on_evaluation=lambda record, result: cls.evaluations.append(result))
        cls.second = optimize(solver_config=numerics, search=SMALL_SEARCH)

    def test_actual_repeatability_fixed_task_and_model_identity(self):
        self.assertEqual(self.first["run_id"], self.second["run_id"])
        first = [(r["analysis_hash"], r["objective"], r["evaluation_status"]) for r in self.first["candidates"]]
        second = [(r["analysis_hash"], r["objective"], r["evaluation_status"]) for r in self.second["candidates"]]
        self.assertEqual(first, second)
        self.assertEqual(len({r["comparability_hash"] for r in self.evaluations}), 1)
        self.assertEqual(len({r["config_hash"] for r in self.evaluations}), 1)
        self.assertEqual(len({r["mission_hash"] for r in self.evaluations}), 1)
        self.assertEqual(self.first["problem"]["mission"], self.first["baseline"]["requirements"])
        self.assertEqual(self.first["problem"]["mission"]["cruise_km"], 500.)

    def test_selected_actual_candidate_is_feasible_in_box_and_best_observed(self):
        report = self.first
        best = report["best"]
        self.assertIsNotNone(best)
        self.assertEqual(best["evaluation_status"], "feasible")
        self.assertTrue(all(c["pass_"] for c in best["constraints"]))
        for variable, (lo, hi) in SMALL_SEARCH["variables"].items():
            self.assertLessEqual(lo, best["inputs"][variable])
            self.assertLessEqual(best["inputs"][variable], hi)
        value = best["mass"]["mass_kg"]
        self.assertLessEqual(value, report["grid_reference"]["best"]["mass"]["mass_kg"])
        observed = [r["mass"]["mass_kg"] for r in self.evaluations if r["demo_constraints_satisfied"] and all(lo <= r["inputs"][k] <= hi for k, (lo, hi) in SMALL_SEARCH["variables"].items())]
        self.assertEqual(value, min(observed))
        self.assertEqual(report["selection"]["closest_constraint"]["normalized_margin"], min(c["normalized_margin"] for c in best["constraints"]))
        self.assertAlmostEqual(report["selection"]["objective_improvement"], report["baseline"]["mass"]["mass_kg"] - value)
        self.assertEqual(best["structure"]["consumed_load_case_hash"], best["load_case_hash"])


if __name__ == "__main__":
    unittest.main()

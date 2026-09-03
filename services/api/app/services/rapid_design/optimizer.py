from collections.abc import Callable

import numpy as np
from scipy.optimize import differential_evolution

from services.api.app.schemas.rapid_design import RapidDesignConfig
from services.api.app.services.rapid_design.evaluator import evaluate_design
from services.api.app.services.rapid_design.geometry_mapper import aircraft_spec_from_result
from services.api.app.services.rapid_design.model_adapter import AerodynamicModelAdapter

ProgressCallback = Callable[[int, int, dict[str, object]], None]
CancelCheck = Callable[[], bool]


def _bounds(config: RapidDesignConfig, inputs: dict[str, float]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for variable in config.design_variables:
        upper = variable.maximum
        if variable.input_upper_bound:
            upper = min(upper, inputs[variable.input_upper_bound])
        if upper < variable.minimum:
            raise ValueError(f"empty optimization range for {variable.key}")
        result.append((variable.minimum, upper))
    return result


def optimize_design(
    *,
    job_id: str,
    inputs: dict[str, float],
    config: RapidDesignConfig,
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> dict[str, object]:
    model = AerodynamicModelAdapter(config.aerodynamics)
    variable_names = [item.key for item in config.design_variables]
    bounds = _bounds(config, inputs)
    evaluations = 0
    generation = 0
    best_any: dict[str, object] | None = None
    best_feasible: dict[str, object] | None = None
    convergence: list[dict[str, object]] = []

    def objective(vector: np.ndarray) -> float:
        nonlocal evaluations, best_any, best_feasible
        if is_cancelled and is_cancelled():
            return 1e12
        design = {key: float(value) for key, value in zip(variable_names, vector, strict=True)}
        evaluation = evaluate_design(design, inputs, config, model)
        evaluations += 1
        if best_any is None or float(evaluation["objective"]) < float(best_any["objective"]):
            best_any = evaluation
        if bool(evaluation["feasible"]):
            mass = float(evaluation["metrics"]["takeoff_mass_kg"])
            if best_feasible is None or mass < float(best_feasible["metrics"]["takeoff_mass_kg"]):
                best_feasible = evaluation
        return float(evaluation["objective"])

    def callback(vector: np.ndarray, convergence_value: float) -> bool:
        nonlocal generation
        generation += 1
        selected = best_feasible or best_any
        if selected is not None:
            metrics = selected["metrics"]
            entry = {
                "iteration": generation,
                "evaluations": evaluations,
                "objective": float(selected["objective"]),
                "takeoff_mass_kg": float(metrics["takeoff_mass_kg"]),
                "feasible": bool(selected["feasible"]),
                "solver_convergence": float(convergence_value),
            }
            convergence.append(entry)
            if on_progress:
                on_progress(generation, config.optimizer.max_iterations, entry)
        return bool(is_cancelled and is_cancelled())

    solver_result = differential_evolution(
        objective,
        bounds,
        strategy="best1bin",
        maxiter=config.optimizer.max_iterations,
        popsize=config.optimizer.population_size,
        seed=config.optimizer.seed,
        polish=config.optimizer.polish,
        callback=callback,
        updating="immediate",
        workers=1,
        tol=0.01,
    )
    if is_cancelled and is_cancelled():
        raise InterruptedError("optimization cancelled")

    selected = best_feasible or best_any
    if selected is None:
        raise RuntimeError("optimizer produced no design evaluations")

    aircraft_spec = aircraft_spec_from_result(job_id, inputs, selected)
    feasible = bool(selected["feasible"])
    warnings = [
        "Concept-level result only; not a certification, safety, or manufacturing analysis.",
        "NeuralFoil is a 2D airfoil surrogate. Finite-wing and fuselage effects use transparent low-order corrections.",
        "Mass and range estimates use configurable empirical equations and should be calibrated before engineering decisions.",
    ]
    if not feasible:
        warnings.insert(
            0,
            "No feasible point was found in the configured search budget; showing the least-violating design.",
        )

    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "status": "feasible" if feasible else "no_feasible_solution_found",
        "feasible": feasible,
        "inputs": inputs,
        "design": selected["design"],
        "metrics": selected["metrics"],
        "mass_breakdown_kg": selected["mass_breakdown_kg"],
        "constraints": selected["constraints"],
        "aircraft_spec": aircraft_spec,
        "convergence": convergence,
        "optimization": {
            "method": config.optimizer.method,
            "seed": config.optimizer.seed,
            "iterations_completed": generation,
            "function_evaluations": evaluations,
            "solver_success": bool(solver_result.success),
            "solver_message": str(solver_result.message),
            "objective": float(selected["objective"]),
        },
        "model_provenance": model.provenance,
        "warnings": warnings,
    }

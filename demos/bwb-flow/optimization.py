"""Reproducible bounded demonstration search; never a global-optimality proof.

Grid and coordinate pattern search share the same full aircraft evaluator. Invalid
evaluations have no artificial objective or numerical penalty. No surrogate training.
"""
from copy import deepcopy
import hashlib
import json
import math
import time

from engine import analyze, DEFAULTS, BOUNDS
from configuration import validate_inputs

OPTIMIZATION_DEFAULTS = {
    'variables': {'span_m': [7.0, 10.0], 'thickness_mm': [0.8, 1.6], 'power_kw': [45., 90.]},
    'objective': 'takeoff_mass_kg', 'grid_levels': 3, 'search_budget': 45,
    'max_rounds': 8, 'initial_step_fraction': .2, 'min_step_fraction': .015, 'seed': 0,
}
ALLOWED_VARIABLES = {'span_m', 'root_chord_m', 'thickness_mm', 'power_kw'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()[:16]


def validate_search(supplied):
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict) or set(supplied)-set(OPTIMIZATION_DEFAULTS):
        raise ValueError('Unknown search settings or invalid search object')
    search = {**deepcopy(OPTIMIZATION_DEFAULTS), **deepcopy(supplied)}
    variables = search['variables']
    if not isinstance(variables, dict) or not 2 <= len(variables) <= 3 or set(variables)-ALLOWED_VARIABLES:
        raise ValueError('Choose 2 or 3 supported continuous hardware variables')
    for name, bounds in variables.items():
        if (not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds) or
                not BOUNDS[name][0] <= bounds[0] < bounds[1] <= BOUNDS[name][1]):
            raise ValueError(f'Invalid optimization bounds: {name}')
    search['variables'] = {name: [float(v) for v in bounds] for name, bounds in variables.items()}
    for key, low, high in [('grid_levels', 2, 5), ('search_budget', 1, 180), ('max_rounds', 1, 20), ('seed', 0, 0)]:
        value = search[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{key} must be an integer in [{low}, {high}]')
    for key in ('initial_step_fraction', 'min_step_fraction'):
        value = search[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .001 <= value <= .5:
            raise ValueError(f'Invalid {key}')
    if search['min_step_fraction'] > search['initial_step_fraction']:
        raise ValueError('Minimum step must not exceed initial step')
    if search['objective'] not in ('takeoff_mass_kg', 'fuel_loaded_kg'):
        raise ValueError('Choose a supported demonstration objective')
    return search


def objective(result, name):
    if result.get('status') != 'demo_converged':
        return None
    value = result.get('mass', {}).get('mass_kg') if name == 'takeoff_mass_kg' else result.get('fuel_loaded_kg')
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def closest(result):
    finite = [c for c in result.get('constraints', result.get('checks', []))
              if isinstance(c.get('normalized_margin'), (int, float)) and math.isfinite(c['normalized_margin'])]
    return min(finite, key=lambda c: c['normalized_margin']) if finite else None


def optimize(inputs=None, model_config=None, solver_config=None, search=None, evaluator=analyze, on_evaluation=None):
    from itertools import product
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError('inputs must be an object')
    # JSON numbers from the UI and Python floats must identify the same hardware.
    fixed = validate_inputs(deepcopy(inputs))
    config, numerics = deepcopy(model_config), deepcopy(solver_config)
    settings = validate_search(search)
    variables = settings['variables']
    keys = sorted(variables)
    started = time.perf_counter()
    records, analyses, cache = [], {}, {}
    actual_counts = {'baseline': 0, 'grid': 0, 'pattern': 0}

    def evaluate(candidate, origin):
        key = digest(candidate)
        if key in cache:
            return cache[key]
        result = evaluator(deepcopy(candidate), model_config=config, solver_config=numerics)
        value = objective(result, settings['objective'])
        state = result.get('evaluation_status') or ('feasible' if result.get('demo_constraints_satisfied') else
                'infeasible' if result.get('status') == 'demo_converged' else 'unknown')
        record = {'index': len(records)+1, 'origin': origin, 'design': result.get('design', {k: candidate[k] for k in keys}),
                  'analysis_id': result['analysis_id'], 'analysis_hash': result['analysis_hash'],
                  'evaluation_status': state, 'objective': value,
                  'tightest_constraint': closest(result), 'failure': result.get('failure')}
        records.append(record)
        analyses[result['analysis_id']] = result
        actual_counts[origin] += 1
        cache[key] = result
        if on_evaluation:
            on_evaluation(deepcopy(record), result)
        return result

    def in_search_box(result):
        return all(lo <= result['inputs'][k] <= hi for k, (lo, hi) in variables.items())

    def rank(result):
        value = objective(result, settings['objective'])
        if result.get('demo_constraints_satisfied') and value is not None:
            return (0, value)
        margins = [c['normalized_margin'] for c in result.get('constraints', result.get('checks', [])) if 'normalized_margin' in c]
        if value is not None and margins:
            return (1, sum(max(0, -v) for v in margins), value)
        return (2,)

    baseline = evaluate(fixed, 'baseline')
    axes = [[lo+(hi-lo)*i/(settings['grid_levels']-1) for i in range(settings['grid_levels'])]
            for lo, hi in (variables[k] for k in keys)]
    grid = [evaluate({**fixed, **dict(zip(keys, values))}, 'grid') for values in product(*axes)]
    feasible_grid = [r for r in grid if r.get('demo_constraints_satisfied') and objective(r, settings['objective']) is not None]
    grid_best = min(feasible_grid, key=lambda r: objective(r, settings['objective'])) if feasible_grid else None
    seeds = grid + ([baseline] if in_search_box(baseline) else [])
    center = min(seeds, key=rank)
    step = settings['initial_step_fraction']
    stop = 'round_budget_exhausted'
    rounds = []
    for round_number in range(1, settings['max_rounds']+1):
        old = center
        if actual_counts['pattern'] >= settings['search_budget']:
            stop = 'evaluation_budget_exhausted'
            break
        for name in keys:
            for direction in (-1, 1):
                if actual_counts['pattern'] >= settings['search_budget']:
                    break
                lo, hi = variables[name]
                point = {**fixed, **{k: center['inputs'][k] for k in keys}}
                point[name] = round(min(hi, max(lo, point[name]+direction*step*(hi-lo))), 10)
                candidate = evaluate(point, 'pattern')
                if rank(candidate) < rank(center):
                    center = candidate
        improved = rank(center) < rank(old)
        rounds.append({'round': round_number, 'step_fraction': step, 'improved': improved,
                       'center_analysis_id': center['analysis_id'], 'objective': objective(center, settings['objective']),
                       'pattern_evaluations': actual_counts['pattern']})
        if not improved:
            step *= .5
        if step < settings['min_step_fraction']:
            stop = 'step_tolerance_reached'
            break
    else:
        stop = 'round_budget_exhausted'
    if actual_counts['pattern'] >= settings['search_budget']:
        stop = 'evaluation_budget_exhausted'
    feasible = [r for r in analyses.values() if in_search_box(r) and r.get('demo_constraints_satisfied') and
                objective(r, settings['objective']) is not None]
    best = min(feasible, key=lambda r: objective(r, settings['objective'])) if feasible else None
    constraint = closest(best) if best else None
    active = [c for c in best.get('constraints', best.get('checks', [])) if c.get('normalized_margin', 1) <= .05] if best else []
    observed_margins = {}
    for evaluation in analyses.values():
        if evaluation.get('status') != 'demo_converged':
            continue
        for check in evaluation.get('constraints', evaluation.get('checks', [])):
            if isinstance(check.get('normalized_margin'), (int,float)):
                observed_margins.setdefault(check['id'], []).append(check['normalized_margin'])
    constant_ids = [key for key, values in observed_margins.items() if len(values)>1 and max(values)-min(values)<1e-12]
    variable_checks = [c for c in best.get('constraints', best.get('checks', [])) if c['id'] not in constant_ids] if best else []
    search_limiting = min(variable_checks, key=lambda c:c['normalized_margin']) if variable_checks else None
    boundary_hits = [k for k, (lo, hi) in variables.items() if min(abs(best['inputs'][k]-lo), abs(best['inputs'][k]-hi)) <= 1e-7*(hi-lo)] if best else []
    base_value = objective(baseline, settings['objective'])
    improvement = base_value-objective(best, settings['objective']) if best and base_value is not None else None
    report = {
        'status': 'candidate_selected' if best else 'no_feasible_candidate',
        'problem': {'mission': baseline['requirements'], 'load_case_definition': baseline.get('load_case_definition'),
                    'fixed_inputs': {k: v for k, v in fixed.items() if k not in variables},
                    'variables': variables, 'objective': settings['objective'], 'settings': settings,
                    'model': baseline.get('model_metadata'), 'configuration': baseline.get('configuration'),
                    'formal_status': 'demonstration_defaults_pending_teacher_decision',
                    'constraint_convention': 'g <= 0; normalized margin >= 0 is satisfied',
                    'active_definition': 'normalized margin <= 0.05; display threshold, not KKT proof',
                    'seed': 0, 'deterministic': True},
        'seed': {'mode': 'existing_geometry', 'M03': 'skipped', 'reason': 'Explicit candidate dimensions supplied; no task sizing claimed', 'inputs': fixed},
        'baseline': baseline, 'best': best, 'candidates': records,
        'grid_reference': {'levels': settings['grid_levels'], 'points': len(grid), 'evaluations': actual_counts['grid'], 'best': grid_best,
                           'role': 'low-dimensional comparison using identical evaluator; not independent physical validation'},
        'search': {'method': 'coordinate_pattern_search', 'evaluations': actual_counts['pattern'], 'budget': settings['search_budget'],
                   'total_evaluations': len(records), 'stop_reason': stop, 'rounds': rounds, 'elapsed_s': time.perf_counter()-started,
                   'selection_rule': 'feasible objective first; among valid infeasible points reduce normalized violation; unknown has no fake objective'},
        'selection': {'reason': 'Minimum declared objective among evaluated feasible candidates inside the search bounds' if best else 'No evaluated feasible candidate; this is not a proof that no feasible aircraft exists',
                      'objective_improvement': improvement, 'closest_constraint': constraint, 'active_constraints': active,
                      'search_limiting_constraint': search_limiting,
                      'fixed_active_constraints': [c for c in active if c['id'] in constant_ids],
                      'constant_constraint_ids': constant_ids,
                      'search_limit_explanation': 'Separates constraints unchanged across observed candidates (e.g. fixed rated loading) from the closest varying constraint; not a sensitivity or KKT proof',
                      'boundary_hits': boundary_hits, 'global_optimality': 'not_proven',
                      'scope': 'Current simplified models only; outer-wing bending, no buckling, torsion, takeoff/landing or independent aircraft validation'},
        'independent_review': {'status': 'not_performed', 'reason': 'No independent CFD/FEA or experimental reference for the selected candidate',
                               'next_action': 'Check candidate with independent references; discrepancies require model/problem revision and reevaluation'},
    }
    report['run_id'] = digest({'problem': report['problem'], 'candidate_hashes': [r['analysis_hash'] for r in records]})
    return report


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('evidence/optimization-example.json'))
    args = parser.parse_args()
    report = optimize()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'run_id': report['run_id'], 'evaluations': report['search']['total_evaluations'],
                      'best_mass_kg': report['best']['mass']['mass_kg'] if report['best'] else None}, ensure_ascii=False))

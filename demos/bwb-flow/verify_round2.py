"""Reproducible HTTP and same-model numerical checks for the review demo.

This does not perform browser testing or independent CFD/FEA/physical validation.
Run against the already-started loopback API; no services are started or stopped.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def browser_numbers(value):
    """Match JSON.stringify's integer-valued numeric representation."""
    if isinstance(value, dict):
        return {key: browser_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [browser_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def request(base, path, payload=None, method='GET'):
    data = None if method == 'GET' else json.dumps(payload, allow_nan=False).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:3981'}
    started = time.perf_counter()
    try:
        response = urlopen(Request(base+path, data=data, headers=headers, method=method), timeout=180)
    except HTTPError as exc:
        response = exc
    with response:
        body = json.loads(response.read().decode('utf-8'))
        return response.status, body, round(time.perf_counter()-started, 4)


def summary(result):
    return {key: result.get(key) for key in (
        'analysis_id', 'analysis_hash', 'design_hash', 'config_hash', 'mission_hash',
        'load_case_hash', 'status', 'numeric_convergence', 'evaluation_status', 'failure',
        'fuel_loaded_kg', 'fuel_residual_kg', 'failure_details')} | {
        'mass_kg': result.get('mass', {}).get('mass_kg'),
        'max_stress_MPa': result.get('structure', {}).get('max_stress_MPa'),
        'tip_deflection_m': result.get('structure', {}).get('tip_deflection_m'),
        'fuel_attempts': len(result.get('iterations', [])),
        'model_id': result.get('model_metadata', {}).get('id'),
        'model_implementation_hash': result.get('model_metadata', {}).get('implementation_hash'),
        'configuration': result.get('configuration'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8842')
    parser.add_argument('--optimization', default='evidence/optimization-example.json')
    parser.add_argument('--output', default='evidence/api-numerical-verification.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = root / args.optimization
    output = root / args.output
    report = {
        'schema': 'bwb-http-numerical-review-v2',
        'executed_at_utc': datetime.now(timezone.utc).isoformat(),
        'api': args.api,
        'scope': 'Real loopback HTTP API checks and selected-candidate numerical refinement with the same physical model.',
        'independent_physical_validation': {'status': 'not_performed', 'reason': 'No independent CFD, FEA, wind-tunnel, flight or material reference is used.'},
        'browser_testing': {'status': 'not_performed_by_this_script'},
        'script_sha256': sha256(Path(__file__)),
        'checks': [],
    }

    def check(name, condition, evidence):
        report['checks'].append({'name': name, 'status': 'passed' if condition else 'failed', 'evidence': evidence})
        print(f"{name}: {'passed' if condition else 'FAILED'}", flush=True)

    try:
        code, defaults, elapsed = request(args.api, '/defaults')
        schema = defaults.get('schema', {})
        check('defaults_controlled_schema', code == 200 and set(defaults.get('inputs', {})) == set(schema.get('inputs', {})) and set(defaults.get('model_config', {})) == set(schema.get('model_config', {})) and set(defaults.get('solver_config', {})) == set(schema.get('solver_config', {})) and bool(schema.get('modules')), {
            'http_status': code, 'elapsed_s': elapsed, 'schema_version': defaults.get('schema', {}).get('version'),
            'input_keys': list(defaults.get('inputs', {})), 'cd0_schema': defaults.get('schema', {}).get('model_config', {}).get('cd0'),
            'cd0_default': defaults.get('model_config', {}).get('cd0'), 'solver_config': defaults.get('solver_config'),
        })
        code, models, elapsed = request(args.api, '/models')
        check('models_real_capability_catalog', code == 200 and bool(models.get('mit_example')) and bool(models.get('mit_input_schema')), {
            'http_status': code, 'elapsed_s': elapsed, 'models': models.get('models'),
            'mit_input_schema': models.get('mit_input_schema'),
        })

        code, baseline, elapsed = request(args.api, '/analyze', {'inputs': defaults['inputs'], 'model_config': defaults['model_config'], 'solver_config': defaults['solver_config']}, 'POST')
        check('analyze_default', code == 200 and baseline.get('numeric_convergence') == 'converged' and baseline.get('evaluation_status') == 'feasible', {'http_status': code, 'elapsed_s': elapsed, 'result': summary(baseline)})
        code, retrieved, elapsed = request(args.api, '/analyses/'+baseline['analysis_id'])
        check('analysis_exact_http_retrieval', code == 200 and retrieved == baseline, {'http_status': code, 'elapsed_s': elapsed, 'analysis_id': baseline['analysis_id'], 'full_json_equality': retrieved == baseline})

        code, aft, elapsed = request(args.api, '/analyze', {'inputs': {**defaults['inputs'], 'tank_offset_mac': .45}}, 'POST')
        invalid_attempts = [item for item in aft.get('iterations', []) if item.get('residual_kg') is None]
        check('aft_tank_valid_branch_not_missed', code == 200 and aft.get('numeric_convergence') == 'converged' and aft.get('evaluation_status') == 'feasible' and bool(invalid_attempts), {
            'http_status': code, 'elapsed_s': elapsed, 'result': summary(aft),
            'invalid_attempts_retained': len(invalid_attempts), 'fuel_solver_diagnostics': aft.get('fuel_solver_diagnostics'),
        })

        code, changed, elapsed = request(args.api, '/analyze', {'inputs': defaults['inputs'], 'model_config': {**defaults['model_config'], 'cd0': .044}}, 'POST')
        delta = changed.get('fuel_loaded_kg', 0)-baseline['fuel_loaded_kg']
        check('cd0_changes_actual_result', code == 200 and changed.get('numeric_convergence') == 'converged' and delta > .1 and changed.get('config_hash') != baseline['config_hash'], {
            'http_status': code, 'elapsed_s': elapsed, 'cd0_before': defaults['model_config']['cd0'], 'cd0_after': .044,
            'fuel_change_kg': delta, 'result': summary(changed),
        })

        invalid_results = []
        for payload in (False, 0, [], {'inputs': False}, {'inputs': 0}, {'inputs': []}, {'inputs': {}, 'model_config': False}, {'inputs': {}, 'solver_config': 0}, {'inputs': {'span_m': False}}):
            code, data, elapsed = request(args.api, '/analyze', payload, 'POST')
            invalid_results.append({'request': payload, 'http_status': code, 'response': data, 'elapsed_s': elapsed})
        check('falsey_invalid_inputs_rejected', all(item['http_status'] == 400 for item in invalid_results), invalid_results)

        code, coefficients, elapsed = request(args.api, '/coefficients', models['mit_example'], 'POST')
        prediction = coefficients.get('prediction', {})
        availability = prediction.get('availability_per_quantity', {})
        check('real_mit_coefficient_boundary', code == 200 and prediction.get('status') == 'coefficient_prediction' and prediction.get('quantities', {}).get('CD', 0) > 0 and availability.get('Cm', {}).get('available') is False, {
            'http_status': code, 'elapsed_s': elapsed, 'response': coefficients,
        })
        code, uq, elapsed = request(args.api, '/uq/status')
        check('no_data_uq_not_evaluated', code == 200 and uq.get('status') == 'not_evaluated', {'http_status': code, 'elapsed_s': elapsed, 'response': uq})

        search = {'variables': {'span_m': [7.8, 8.2], 'thickness_mm': [1.0, 1.4]}, 'grid_levels': 2, 'search_budget': 3, 'max_rounds': 1, 'seed': 0}
        browser_payload = browser_numbers({'inputs': defaults['inputs'], 'model_config': defaults['model_config'], 'solver_config': defaults['solver_config'], 'search': search})
        code, small_search, elapsed = request(args.api, '/optimize', browser_payload, 'POST')
        check('small_http_optimizer_shared_evaluator', code == 200 and small_search.get('status') == 'candidate_selected' and small_search.get('best', {}).get('evaluation_status') == 'feasible' and len(small_search.get('candidates', [])) >= 4, {
            'http_status': code, 'elapsed_s': elapsed, 'request_search': search, 'run_id': small_search.get('run_id'),
            'status': small_search.get('status'), 'candidates': small_search.get('candidates'),
            'search': small_search.get('search'), 'best': summary(small_search.get('best', {})),
            'scope': 'HTTP smoke search only; not the full default optimization experiment.',
        })

        from optimization import optimize
        cli_search = optimize(defaults['inputs'], model_config=defaults['model_config'], solver_config=defaults['solver_config'], search=search)
        def signatures(result):
            return [{key: candidate.get(key) for key in ('index', 'origin', 'analysis_hash', 'evaluation_status', 'objective')} for candidate in result['candidates']]
        http_signature, cli_signature = signatures(small_search), signatures(cli_search)
        check('integer_browser_json_matches_cli_optimization', http_signature == cli_signature and small_search.get('run_id') == cli_search.get('run_id'), {
            'http_run_id': small_search.get('run_id'), 'cli_run_id': cli_search.get('run_id'),
            'http_candidates': http_signature, 'cli_candidates': cli_signature,
            'http_search': small_search.get('search'), 'cli_search': cli_search.get('search'),
            'input_example': {'browser_span_m_type': type(browser_payload['inputs']['span_m']).__name__, 'cli_span_m_type': type(defaults['inputs']['span_m']).__name__},
            'scope': 'Same local evaluator, settings and physical values; compares browser-style integer-valued JSON with native defaults. UUID analysis_id is deliberately excluded.',
        })

        experiment = json.loads(source.read_text(encoding='utf-8'))
        best = experiment['best']
        refined_solver = {**best['configuration']['solver'], 'mission_steps': 72, 'load_strips': 200}
        code, refined, elapsed = request(args.api, '/analyze', {'inputs': best['inputs'], 'model_config': best['configuration']['model'], 'solver_config': refined_solver}, 'POST')
        metrics = {
            'fuel_loaded_kg': (best.get('fuel_loaded_kg'), refined.get('fuel_loaded_kg')),
            'takeoff_mass_kg': (best.get('mass', {}).get('mass_kg'), refined.get('mass', {}).get('mass_kg')),
            'max_stress_MPa': (best.get('structure', {}).get('max_stress_MPa'), refined.get('structure', {}).get('max_stress_MPa')),
            'tip_deflection_m': (best.get('structure', {}).get('tip_deflection_m'), refined.get('structure', {}).get('tip_deflection_m')),
        }
        metric_deltas = {name: {'original': a, 'refined': b, 'delta': b-a if a is not None and b is not None else None, 'relative_delta': (b-a)/abs(a) if a not in (None, 0) and b is not None else None} for name, (a, b) in metrics.items()}
        original_constraints = {item['id']: item for item in best['constraints']}
        constraint_deltas = []
        for item in refined.get('constraints', []):
            old = original_constraints.get(item['id'])
            if old is None:
                continue
            constraint_deltas.append({
                'id': item['id'], 'name': item['name'], 'unit': item['unit'], 'sense': item['sense'],
                'original_value': old['value'], 'refined_value': item['value'], 'value_delta': item['value']-old['value'],
                'limit': item['limit'], 'original_g': old['g'], 'refined_g': item['g'], 'g_delta': item['g']-old['g'],
                'original_normalized_margin': old['normalized_margin'], 'refined_normalized_margin': item['normalized_margin'],
                'normalized_margin_delta': item['normalized_margin']-old['normalized_margin'],
                'original_pass': old['pass_'], 'refined_pass': item['pass_'],
                'original_condition_id': old.get('source', {}).get('condition_id'), 'refined_condition_id': item.get('source', {}).get('condition_id'),
                'refined_load_case_hash': item.get('source', {}).get('load_case_hash'),
            })
        check('selected_candidate_same_model_numerical_refinement', code == 200 and refined.get('numeric_convergence') == 'converged' and refined.get('evaluation_status') == 'feasible' and refined['configuration']['model'] == best['configuration']['model'] and refined['design_hash'] == best['design_hash'], {
            'http_status': code, 'elapsed_s': elapsed, 'source_optimization': str(source.relative_to(root)),
            'source_sha256': sha256(source), 'source_run_id': experiment.get('run_id'),
            'expected_review_run_match': experiment.get('run_id') == 'd50feb01ebee86f4',
            'original': summary(best), 'refined': summary(refined), 'metrics': metric_deltas, 'constraint_deltas': constraint_deltas,
            'conclusion_scope': 'Same-model numerical sensitivity check with mission steps 36→72 and load strips 100→200. One refinement is not an asymptotic convergence proof and not independent physical validation.',
        })
    except Exception as exc:
        report['checks'].append({'name': 'verification_execution', 'status': 'failed', 'exception_type': type(exc).__name__, 'message': str(exc)})
        print(type(exc).__name__, str(exc), flush=True)
    report['status'] = 'passed' if report['checks'] and all(item['status'] == 'passed' for item in report['checks']) else 'failed'
    report['executed_check_count'] = len(report['checks'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'output': str(output)}, ensure_ascii=True), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

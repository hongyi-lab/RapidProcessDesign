"""Reproduce the preserved v1 bugs and current v2 numerical evidence.

No external resources or prior .run files required. This does not validate
aircraft physics. Run from this directory: python verify_core_evidence.py
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import types
import unittest
import zlib

import engine
from test_core_v2 import LEGACY_ENGINE_B85


HERE = Path(__file__).resolve().parent


def write(name, data):
    output = HERE / 'evidence' / name
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def preserved_evidence():
    source=zlib.decompress(base64.b85decode(LEGACY_ENGINE_B85))
    source_hash=hashlib.sha256(source).hexdigest()
    assert source_hash=='c693b1e7462f081518b937ae9fa426803c70c1cd2167cb84eed0c6a6415ac751'
    legacy=types.ModuleType('preserved_bwb_v1')
    exec(compile(source,'preserved_engine_v1.py','exec'),legacy.__dict__)
    baseline=legacy.analyze()
    aft=legacy.analyze({'tank_offset_mac':.45})
    legacy.ASSUMPTIONS['cd0']=.044
    changed=legacy.analyze()
    loaded=legacy.analyze({'payload_kg':120})
    p={**legacy.DEFAULTS,'tank_offset_mac':.45};g=legacy.geometry(p)
    lo,hi=26.103315224794457,27.346330235498954
    for _ in range(45):
        mid=(lo+hi)/2
        residual=mid-(1.15*legacy.mission(p,g,mid)['burn_kg']+1.5)
        if residual>0:hi=mid
        else:lo=mid
    root=(lo+hi)/2
    return dict(source_sha256=source_hash,snapshot='dd6244af96214545a698470c18a148107c5017fc',
        evidence_kind='reexecuted_preserved_v1_source; historical model, not current v2 output',
        baseline={k:baseline[k] for k in ('status','fuel_loaded_kg','design_hash')},
        leak={k:aft[k] for k in ('status','failure','iterations')},
        independent_same_model_root_kg=root,
        residual_kg=root-(1.15*legacy.mission(p,g,root)['burn_kg']+1.5),
        config_bug=dict(exported_cd0=changed['assumptions']['cd0'],fuel_before=baseline['fuel_loaded_kg'],fuel_after=changed['fuel_loaded_kg']),
        hardware_bug=dict(design_hashes=[baseline['design_hash'],loaded['design_hash']],
            hardware_masses=[r['mass']['mass_kg']-r['inputs']['payload_kg']-r['fuel_loaded_kg'] for r in (baseline,loaded)]))


def current_evidence():
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromNames(['test_engine','test_core_v2'])
    checks=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
    if not checks.wasSuccessful():
        raise RuntimeError(stream.getvalue())
    baseline=engine.analyze()
    aft=engine.analyze({'tank_offset_mac':.45})
    higher=engine.analyze(model_config={'cd0':.044})
    partial=engine.analyze({'load_factor':5,'power_kw':50})
    selected_inputs={'span_m':7,'thickness_mm':.8,'power_kw':59.625}
    selected=engine.analyze(selected_inputs)
    case=baseline['structure']['load_case']
    loaded=engine.analyze({'payload_kg':120})
    rated=engine.analyze({'rated_payload_kg':120})
    file_hashes={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in (
        'engine.py','configuration.py','test_engine.py','test_core_v2.py','verify_core_evidence.py')}
    return dict(model=engine.VERSION,implementation_hash=engine.IMPLEMENTATION_HASH,source_sha256=file_hashes,
        baseline=dict(fuel_kg=baseline['fuel_loaded_kg'],mass_kg=baseline['mass']['mass_kg'],
            stress_MPa=baseline['structure']['max_stress_MPa'],residual_kg=baseline['fuel_residual_kg'],status=baseline['status']),
        repaired_aft_tank=dict(fuel_kg=aft['fuel_loaded_kg'],status=aft['status'],diagnostics=aft['fuel_solver_diagnostics']),
        configuration_effect=dict(cd0_default=.022,cd0_changed=.044,default_fuel_kg=baseline['fuel_loaded_kg'],changed_fuel_kg=higher['fuel_loaded_kg']),
        fixed_hardware=dict(design_hashes=[baseline['design_hash'],loaded['design_hash']],
            hardware_masses_kg=[baseline['mass']['hardware_mass_kg'],loaded['mass']['hardware_mass_kg']],
            rated_sizing_mass_change_kg=rated['mass']['hardware_mass_kg']-baseline['mass']['hardware_mass_kg']),
        load_interface=dict(produced_hash=case['hash'],consumed_hash=baseline['structure']['consumed_load_case_hash'],
            mass_error_kg=case['structural_mass_error_kg'],root_force_error_N=baseline['structure']['load_interface_force_error_N'],
            root_moment_error_Nm=baseline['structure']['load_interface_moment_error_Nm']),
        partial_state=dict(status=partial['status'],numeric_convergence=partial['numeric_convergence'],
            mission_retained='mission' in partial,failure=partial['failure'],module=partial['failure_details']['module']),
        selected_example_inputs=selected_inputs,
        selected_maneuver_constraint=next(c for c in selected['constraints'] if c['id']=='maneuver_power'),
        tests=dict(scope='core only; full-suite aggregate is verification-v2.json',count=checks.testsRun,
            failures=len(checks.failures),errors=len(checks.errors),status='passed',log=stream.getvalue()),
        verification_scope='Numerical regression and analytic implementation checks; no independent aircraft CFD/FEA validation',
        engineering_validation='not_performed')


def main():
    old=preserved_evidence()
    current=current_evidence()
    write('pre-fix-core.json',old)
    write('core-v2-evidence.json',current)
    print(json.dumps(dict(status='written',files=['evidence/pre-fix-core.json','evidence/core-v2-evidence.json'],
                          core_tests=current['tests']['count'],implementation_hash=engine.IMPLEMENTATION_HASH)))


if __name__=='__main__':
    main()

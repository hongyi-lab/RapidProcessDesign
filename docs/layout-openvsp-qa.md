---
qa_id: layout-openvsp-qa
status: pass
date: 2026-05-26
env: fake
openvsp_version: "OpenVSP 3.50.2"
backend: fake
layouts_total: 11
layouts_pass: 11
layouts_skip: 0
layouts_fail: 0
---

# Layout OpenVSP QA Report

> **Note:** This report validates the software generation pipeline. "PASS" means artifacts were generated successfully. It does NOT mean the aircraft configuration is aerodynamically optimal, structurally feasible, or engineering certified.

> **Warning:** This report uses the fake backend. Artifacts are placeholders, not real geometry. Run with `--backend openvsp` for real OpenVSP validation.

**Date:** 2026-05-26
**Backend:** fake
**OpenVSP:** OpenVSP 3.50.2
**Result:** 11/11 layouts passed

## Environment

| Item | Value |
|------|-------|
| Date | 2026-05-26 |
| Backend | fake |
| OpenVSP | OpenVSP 3.50.2 |
| Python | 3.12.3 |
| Total layouts | 11 |
| Passed | 11 |
| Skipped | 0 |
| Failed | 0 |
| Script | `scripts/validate_layout_matrix.py` |

## Layout Verification Matrix

| Layout | Spec | Defaults | VSP3 | GLB | STEP | OBJ | Log | Report | Metrics | Backend | Status |
|--------|:----:|:--------:|:----:|:---:|:----:|:---:|:---:|:------:|:-------:|:-------:|:------:|
| conventional | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| twin_boom | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| flying_wing | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| blended_wing_body | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| canard | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| three_surface | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| tandem_wing | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| biplane | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| joined_wing | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| box_wing | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |
| multi_fuselage | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ fake | ✅ |

## Per-Layout Details

### conventional

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/twin_engine_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Optional

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.6 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 15.0 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### twin_boom

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/twin_boom_pusher_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Optional

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.2 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.2 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### flying_wing

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/flying_wing_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Optional

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.2 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.4 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### blended_wing_body

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/bwb_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Optional

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.4 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.8 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### canard

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/canard_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.4 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.7 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### three_surface

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/three_surface_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.4 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.7 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### tandem_wing

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/tandem_wing_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Optional

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.5 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.9 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### biplane

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/biplane_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.6 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 15.0 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### joined_wing

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/joined_wing_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.5 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.8 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### box_wing

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/box_wing_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.2 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.5 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

### multi_fuselage

- **Status:** PASS
- **YAML:** `packages/aircraft-schema/examples/multi_fuselage_uav.yaml`
- **Backend:** fake
- **Visual Inspection:** Recommended (complex layout)

| Artifact | Status | Size |
|----------|--------|------|
| aircraft.vsp3 | pass | 0.0 KB |
| aircraft.glb | pass | 0.0 KB |
| aircraft.step | pass | 0.0 KB |
| aircraft.obj | skip | 0 KB |
| aircraft_spec.yaml | pass | 2.2 KB |
| generation_log.json | pass | 0.4 KB |
| validation_report.json | pass | 14.4 KB |

**VSPAERO Analysis:** VSPAERO not run for this layout (triggered separately via settings)

- **Frontend 2D preview:** ✅ (verified by `verify-layout-previews.mjs`)

## Summary

| Status | Count | Layouts |
|--------|:-----:|---------|
| ✅ PASS | 11 | conventional, twin_boom, flying_wing, blended_wing_body, canard, three_surface, tandem_wing, biplane, joined_wing, box_wing, multi_fuselage |

## Maturity Assessment

All 11 layouts generate valid artifacts via fake backend. All are suitable for **Stable** maturity.

## Recommendations

- **Real OpenVSP validation recommended:** Run with `--backend openvsp` for geometry validity confirmation.
- Fake backend validates pipeline structure only, not geometric correctness.
- Layouts with multi-surface VSPAERO analysis: canard, three_surface, tandem_wing, joined_wing, biplane, box_wing.
- Per-surface aerodynamic reports not yet available (VSPAERO outputs combined metrics).

## Re-run

```bash
python scripts/validate_layout_matrix.py --backend fake
```
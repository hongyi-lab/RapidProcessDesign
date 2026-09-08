from copy import deepcopy
from math import pi

import aerosandbox as asb
import numpy as np
import pytest

from services.api.app.schemas.rapid_design import BwbAnalysisCondition, ConventionalV2Design
from services.api.app.services.rapid_design.config_loader import load_mission_demo_profile
from services.api.app.services.rapid_design.cruise import integrate_range_km
from services.api.app.services.rapid_design.families.conventional_v2.aerodynamics import (
    AircraftAerodynamics,
    section_coordinates,
)
from services.api.app.services.rapid_design.families.conventional_v2.geometry import (
    decode_conventional_geometry,
)
from services.api.app.services.rapid_design.families.conventional_v2.presets import (
    CONVENTIONAL_V2_PRESETS,
)
from services.api.app.services.rapid_design.families.registry import registry
from services.api.app.services.rapid_design.mission_demo import evaluate_mission_demo_candidate


def aircraft(preset="long_endurance_uav", **changes):
    geometry, _ = decode_conventional_geometry(
        ConventionalV2Design(**{**CONVENTIONAL_V2_PRESETS[preset], **changes}), preset,
    )
    condition = BwbAnalysisCondition(
        altitude_m=2000, speed_kmh=220, alpha_min_deg=-4, alpha_max_deg=12, alpha_samples=25,
    )
    return AircraftAerodynamics(geometry, condition)


def candidate(*, preset="long_endurance_uav", inputs=None, family_registry=registry):
    return evaluate_mission_demo_candidate(
        profile=load_mission_demo_profile(), family_id="conventional_v2", preset_id=preset,
        design=CONVENTIONAL_V2_PRESETS[preset], sizing={"fuel_mass_kg": 200},
        inputs=inputs or {}, family_registry=family_registry,
    )


def test_section_coordinates_match_preview_camber_and_closed_trailing_edge():
    coordinates = section_coordinates(0.15, 0.04, 0.4)
    assert coordinates[0] == pytest.approx([1, 0], abs=1e-12)
    assert coordinates[-1] == pytest.approx([1, 0], abs=1e-12)
    top = coordinates[:101][::-1]
    bottom = np.vstack([[0, 0], coordinates[101:]])
    mean = (top[:, 1] + bottom[:, 1]) / 2
    assert max(mean) == pytest.approx(0.04, abs=1e-4)
    assert max(top[:, 1] - bottom[:, 1]) == pytest.approx(0.15, abs=3e-4)


def test_symmetric_wing_agrees_with_independent_vlm_and_finite_wing_limit():
    # A rectangular AR=8 wing, attached flow: independent numerical/analytical checks,
    # not an assertion against a saved output of the implementation being tested.
    wing = asb.Wing(symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=1, airfoil=asb.Airfoil("naca0012")),
        asb.WingXSec(xyz_le=[0, 4, 0], chord=1, airfoil=asb.Airfoil("naca0012")),
    ])
    plane = asb.Airplane(wings=[wing], xyz_ref=[0.25, 0, 0])
    buildup = asb.AeroBuildup(
        airplane=plane, op_point=asb.OperatingPoint(velocity=50, alpha=np.array([-1., 0., 1.])),
    ).run()
    vlm = asb.VortexLatticeMethod(
        airplane=plane, op_point=asb.OperatingPoint(velocity=50, alpha=1),
        spanwise_resolution=12, chordwise_resolution=6,
    ).run()
    slope = (buildup["CL"][2] - buildup["CL"][0]) / np.radians(2)
    assert abs(buildup["CL"][1]) < 1e-5
    assert abs(buildup["Cm"][1]) < 1e-5
    assert slope == pytest.approx(2 * pi * 8 / (8 + 2), rel=0.15)
    assert buildup["CL"][2] == pytest.approx(float(vlm["CL"]), rel=0.15)
    assert np.all(buildup["CD"] > 0)


def test_actual_camber_and_twist_change_aerodynamics():
    baseline = aircraft()
    original = baseline.evaluate([0., 3.])
    for wing in baseline.airplane.wings:
        if wing.name == "main_wing":
            for section in wing.xsecs:
                section.airfoil = asb.Airfoil("naca0012").to_kulfan_airfoil()
    symmetric = baseline.evaluate([0., 3.])
    twisted = aircraft(wing_twist_tip_deg=-6).evaluate([0., 3.])
    assert np.all(original["cl"] > symmetric["cl"] + 0.1)
    assert not np.allclose(original["cl"], twisted["cl"], atol=0.01)


@pytest.mark.parametrize("preset", list(CONVENTIONAL_V2_PRESETS))
def test_cruise_solves_force_and_moment_balance_at_all_mass_stations(preset):
    result = candidate(preset=preset)
    cruise = result["cruise_consistency"]
    for point in cruise["mass_stations"]:
        assert point["status"] == "supported"
        assert abs(point["lift_residual_n"]) < 5
        assert abs(point["cm"]) < 2e-4
        assert abs(point["elevator_deg"]) <= 25
        assert point["confidence"] >= 0.8
    assert cruise["enters_score"] and cruise["enters_range_estimate"]
    assert result["provenance"]["analyze"]["uses_external_weights"] is True
    assert result["provenance"]["analyze"]["software_versions"]["neuralfoil"] == "0.3.3"


def test_aft_cg_reduces_static_margin_and_changes_trim():
    model = aircraft("fast_cruise_recon")
    forward = model.trim([1100], cg_mac_fraction=0.25)[0]
    aft = model.trim([1100], cg_mac_fraction=0.55)[0]
    assert forward["static_margin"] > 0.05
    assert aft["static_margin"] < 0
    assert abs(forward["elevator_deg"] - aft["elevator_deg"]) > 1
    result = candidate(preset="fast_cruise_recon", inputs={"cg_percent_mac": 55})
    assert result["cruise_consistency"]["reason_code"] == "static_margin_not_supported"
    assert result["metrics"]["achieved_range_km"] == 0
    assert result["feasible"] is False


def test_insufficient_power_prevents_a_supported_range():
    result = candidate(inputs={"shaft_power_per_engine_kw": 20})
    assert result["cruise_consistency"]["reason_code"] == "insufficient_power"
    assert result["metrics"]["shaft_power_required_kw"] > result["metrics"]["shaft_power_available_kw"]
    assert result["metrics"]["achieved_range_km"] == 0
    assert result["feasible"] is False


def test_low_speed_high_altitude_does_not_extrapolate_a_feasible_cruise():
    result = candidate(inputs={"cruise_speed_kmh": 80, "cruise_altitude_m": 11000,
                               "payload_mass_kg": 500})
    assert result["cruise_consistency"]["checks"]["trim"] is False
    assert result["metrics"]["achieved_range_km"] == 0
    assert result["feasible"] is False


def test_constant_power_range_has_correct_fuel_and_hour_units():
    distance = integrate_range_km(
        usable_fuel_kg=120, speed_kmh=220, shaft_powers_kw=[60, 60, 60], bsfc_kg_per_kwh=0.3,
    )
    assert distance == pytest.approx((120 / (60 * 0.3)) * 220)


def test_range_and_score_do_not_use_neutral_polar_peak():
    class ChangedPeak:
        manifest = registry.manifest

        @staticmethod
        def analyze(request):
            result = deepcopy(registry.analyze(request))
            result.analysis.summary.max_ld = 1000.0
            result.summary.max_ld = 1000.0
            return result

    baseline, changed = candidate(), candidate(family_registry=ChangedPeak())
    assert changed["analysis_summary"]["max_ld"] == 1000
    assert changed["metrics"]["achieved_range_km"] == baseline["metrics"]["achieved_range_km"]
    assert changed["objective"] == baseline["objective"]


def test_power_rating_enters_mass_estimate_instead_of_being_free():
    low = candidate(inputs={"shaft_power_per_engine_kw": 100})
    high = candidate(inputs={"shaft_power_per_engine_kw": 300})
    assert high["metrics"]["propulsion_mass_kg"] > low["metrics"]["propulsion_mass_kg"]
    assert high["metrics"]["takeoff_mass_kg"] > low["metrics"]["takeoff_mass_kg"]

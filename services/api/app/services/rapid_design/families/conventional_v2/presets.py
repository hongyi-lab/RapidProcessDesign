from types import MappingProxyType

# The three presets are clean-room archetypes. Public aircraft dimensions are
# used only as order-of-magnitude ratio anchors; no external CAD is imported.
CONVENTIONAL_V2_PRESETS = MappingProxyType(
    {
        "long_endurance_uav": MappingProxyType(
            {
                "fuselage_length_m": 10.8,
                "fineness_ratio": 12.5,
                "nose_length_ratio": 0.18,
                "cabin_fullness": 0.90,
                "tailcone_length_ratio": 0.36,
                "section_ovality": 0.86,
                "wing_span_m": 20.2,
                "wing_area_m2": 22.0,
                "wing_root_x_ratio": 0.32,
                "wing_vertical_ratio": 0.12,
                "wing_sweep_deg": 3.0,
                "wing_taper_ratio": 0.27,
                "wing_dihedral_deg": 5.5,
                "wing_twist_tip_deg": -3.5,
                "wing_thickness_ratio": 0.15,
                "tail_arm_ratio": 0.82,
                "tail_scale": 0.92,
            }
        ),
        "fast_cruise_recon": MappingProxyType(
            {
                "fuselage_length_m": 10.8,
                "fineness_ratio": 11.2,
                "nose_length_ratio": 0.27,
                "cabin_fullness": 0.80,
                "tailcone_length_ratio": 0.28,
                "section_ovality": 0.92,
                "wing_span_m": 12.8,
                "wing_area_m2": 18.0,
                "wing_root_x_ratio": 0.38,
                "wing_vertical_ratio": -0.10,
                "wing_sweep_deg": 22.0,
                "wing_taper_ratio": 0.25,
                "wing_dihedral_deg": 2.0,
                "wing_twist_tip_deg": -2.0,
                "wing_thickness_ratio": 0.095,
                "tail_arm_ratio": 0.78,
                "tail_scale": 0.82,
            }
        ),
        "payload_utility": MappingProxyType(
            {
                "fuselage_length_m": 11.2,
                "fineness_ratio": 7.3,
                "nose_length_ratio": 0.12,
                "cabin_fullness": 1.12,
                "tailcone_length_ratio": 0.24,
                "section_ovality": 1.22,
                "wing_span_m": 15.0,
                "wing_area_m2": 34.0,
                "wing_root_x_ratio": 0.34,
                "wing_vertical_ratio": 0.32,
                "wing_sweep_deg": 4.0,
                "wing_taper_ratio": 0.55,
                "wing_dihedral_deg": 2.5,
                "wing_twist_tip_deg": -1.5,
                "wing_thickness_ratio": 0.17,
                "tail_arm_ratio": 0.80,
                "tail_scale": 1.30,
            }
        ),
    }
)

PRESET_PROPULSION = MappingProxyType(
    {
        "long_endurance_uav": "rear_pusher",
        "fast_cruise_recon": "nose_tractor",
        "payload_utility": "twin_wing_mounted",
    }
)

PRESET_ARCHETYPES = MappingProxyType(
    {
        "long_endurance_uav": "male_uav_v_tail",
        "fast_cruise_recon": "fast_tractor_t_tail",
        "payload_utility": "high_wing_twin_utility",
    }
)

PRESET_REFERENCE_BASIS = MappingProxyType(
    {
        "long_endurance_uav": MappingProxyType(
            {
                "source_name": "USAF MQ-9 Reaper fact sheet",
                "source_url": (
                    "https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104470/"
                    "mq9-reaper/mq-9-reaper/"
                ),
                "published_length_m": 11.0,
                "published_span_m": 20.1,
                "usage_note": "Span-to-length scale anchor for a long-endurance pusher UAV.",
            }
        ),
        "fast_cruise_recon": MappingProxyType(
            {
                "source_name": "Daher TBM 960 specifications",
                "source_url": "https://www.tbm.aero/page/tbm960",
                "published_length_m": 10.74,
                "published_span_m": 12.83,
                "usage_note": "Scale anchor for a fast single-engine tractor archetype.",
            }
        ),
        "payload_utility": MappingProxyType(
            {
                "source_name": "Cessna SkyCourier official specifications",
                "source_url": (
                    "https://cessna.txtav.com/en/turboprop/skycourier-freighter"
                ),
                "published_length_m": 16.8,
                "published_span_m": 22.02,
                "usage_note": "Ratio anchor for a high-wing twin-engine utility archetype.",
            }
        ),
    }
)

from types import MappingProxyType

CONVENTIONAL_V2_PRESETS = MappingProxyType(
    {
        "long_endurance_uav": MappingProxyType(
            {
                "fuselage_length_m": 9.6,
                "fineness_ratio": 12.0,
                "nose_length_ratio": 0.16,
                "cabin_fullness": 0.85,
                "tailcone_length_ratio": 0.38,
                "section_ovality": 0.90,
                "wing_span_m": 19.0,
                "wing_area_m2": 20.0,
                "wing_root_x_ratio": 0.30,
                "wing_vertical_ratio": 0.08,
                "wing_sweep_deg": 4.0,
                "wing_taper_ratio": 0.32,
                "wing_dihedral_deg": 5.0,
                "wing_twist_tip_deg": -3.0,
                "wing_thickness_ratio": 0.14,
                "tail_arm_ratio": 0.80,
                "tail_scale": 0.85,
            }
        ),
        "fast_cruise_recon": MappingProxyType(
            {
                "fuselage_length_m": 11.8,
                "fineness_ratio": 14.0,
                "nose_length_ratio": 0.25,
                "cabin_fullness": 0.75,
                "tailcone_length_ratio": 0.30,
                "section_ovality": 0.82,
                "wing_span_m": 14.5,
                "wing_area_m2": 24.0,
                "wing_root_x_ratio": 0.36,
                "wing_vertical_ratio": -0.05,
                "wing_sweep_deg": 27.0,
                "wing_taper_ratio": 0.26,
                "wing_dihedral_deg": 3.0,
                "wing_twist_tip_deg": -2.0,
                "wing_thickness_ratio": 0.10,
                "tail_arm_ratio": 0.76,
                "tail_scale": 0.78,
            }
        ),
        "payload_utility": MappingProxyType(
            {
                "fuselage_length_m": 10.2,
                "fineness_ratio": 7.2,
                "nose_length_ratio": 0.12,
                "cabin_fullness": 1.15,
                "tailcone_length_ratio": 0.26,
                "section_ovality": 1.12,
                "wing_span_m": 16.0,
                "wing_area_m2": 33.0,
                "wing_root_x_ratio": 0.31,
                "wing_vertical_ratio": 0.28,
                "wing_sweep_deg": 7.0,
                "wing_taper_ratio": 0.48,
                "wing_dihedral_deg": 3.0,
                "wing_twist_tip_deg": -2.0,
                "wing_thickness_ratio": 0.16,
                "tail_arm_ratio": 0.77,
                "tail_scale": 1.25,
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


from types import MappingProxyType

DEFAULT_BWB_DESIGN = MappingProxyType(
    {
        "c1_m": 6.0,
        "c2_ratio": 0.78,
        "c3_ratio": 0.48,
        "c4_ratio": 0.18,
        "b1_ratio": 0.32,
        "b2_ratio": 0.45,
        "b3_ratio": 0.70,
        "x3_ratio": 0.25,
        "sweep_inner_deg": 38.0,
        "sweep_outer_deg": 28.0,
        "thickness_ratio": 0.12,
        "twist_tip_deg": -2.0,
    }
)

BWB_PRESETS = MappingProxyType({"balanced_concept": DEFAULT_BWB_DESIGN})


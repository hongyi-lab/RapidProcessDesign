from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RapidInputDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    minimum: float
    maximum: float
    step: float
    default: float
    kind: Literal["requirement", "constraint"]

    @model_validator(mode="after")
    def default_is_in_range(self) -> "RapidInputDefinition":
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError(f"default for {self.key} is outside its range")
        return self


class RapidVariableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    minimum: float
    maximum: float
    input_upper_bound: str | None = None


class RapidOptimizerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["differential_evolution"]
    seed: int = 2711
    max_iterations: int = Field(default=9, ge=1, le=100)
    population_size: int = Field(default=5, ge=3, le=30)
    polish: bool = False


class RapidAerodynamicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["neuralfoil", "analytic"] = "neuralfoil"
    model_size: str = "medium"
    min_analysis_confidence: float = Field(default=0.55, ge=0, le=1)
    alpha_min_deg: float = -3
    alpha_max_deg: float = 14
    alpha_samples: int = Field(default=18, ge=5, le=100)
    oswald_efficiency: float = Field(default=0.82, gt=0, le=1)
    reserve_fuel_fraction: float = Field(default=0.15, ge=0, lt=1)
    equivalent_tsfc_per_second: float = Field(default=0.00017, gt=0)


class RapidMassModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wing_areal_density_kg_m2: float
    wing_span_penalty_kg_m: float
    fuselage_shell_density_kg_m2: float
    systems_base_mass_kg: float
    systems_payload_fraction: float
    propulsion_base_mass_kg: float
    landing_gear_fraction: float


class RapidDesignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    title: str
    description: str
    inputs: list[RapidInputDefinition]
    design_variables: list[RapidVariableDefinition]
    optimizer: RapidOptimizerConfig
    aerodynamics: RapidAerodynamicsConfig
    mass_model: RapidMassModelConfig


class RapidDesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, float]


class RapidDesignJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float = Field(ge=0, le=1)
    stage: str
    error: str | None = None
    created_at: str
    updated_at: str


# ``bwb_v1`` is a project-original, conservative conceptual-design domain.  The
# numerical limits are deliberately kept here next to the request schema so the
# API validator and the domain report cannot silently drift apart.
BWB_V1_DESIGN_BOUNDS: dict[str, tuple[float, float, str]] = {
    "c1_m": (2.0, 12.0, "m"),
    "c2_ratio": (0.55, 0.95, "-"),
    "c3_ratio": (0.25, 0.70, "-"),
    "c4_ratio": (0.08, 0.35, "-"),
    "b1_ratio": (0.15, 0.60, "-"),
    "b2_ratio": (0.20, 0.80, "-"),
    "b3_ratio": (0.30, 1.20, "-"),
    "x3_ratio": (0.00, 0.80, "-"),
    "sweep_inner_deg": (20.0, 55.0, "deg"),
    "sweep_outer_deg": (15.0, 45.0, "deg"),
    "thickness_ratio": (0.08, 0.18, "-"),
    "twist_tip_deg": (-6.0, 2.0, "deg"),
}

BWB_V1_CONDITION_BOUNDS: dict[str, tuple[float, float, str]] = {
    "altitude_m": (0.0, 11_000.0, "m"),
    "speed_kmh": (80.0, 500.0, "km/h"),
    "alpha_min_deg": (-10.0, 15.0, "deg"),
    "alpha_max_deg": (-5.0, 20.0, "deg"),
    "alpha_samples": (5.0, 81.0, "count"),
}


class BwbV1Design(BaseModel):
    """Typed clean-room design vector for the first BWB family."""

    model_config = ConfigDict(extra="forbid")

    c1_m: float = Field(ge=2.0, le=12.0)
    c2_ratio: float = Field(ge=0.55, le=0.95)
    c3_ratio: float = Field(ge=0.25, le=0.70)
    c4_ratio: float = Field(ge=0.08, le=0.35)
    b1_ratio: float = Field(ge=0.15, le=0.60)
    b2_ratio: float = Field(ge=0.20, le=0.80)
    b3_ratio: float = Field(ge=0.30, le=1.20)
    x3_ratio: float = Field(ge=0.00, le=0.80)
    sweep_inner_deg: float = Field(ge=20.0, le=55.0)
    sweep_outer_deg: float = Field(ge=15.0, le=45.0)
    thickness_ratio: float = Field(ge=0.08, le=0.18)
    twist_tip_deg: float = Field(ge=-6.0, le=2.0)

    @model_validator(mode="after")
    def chord_ratios_decrease_outboard(self) -> "BwbV1Design":
        minimum_gap = 0.01
        if (
            self.c2_ratio - self.c3_ratio + 1e-12 < minimum_gap
            or self.c3_ratio - self.c4_ratio + 1e-12 < minimum_gap
        ):
            raise ValueError(
                "chord ratios must decrease outboard with a minimum gap of 0.01"
            )
        return self


class BwbAnalysisCondition(BaseModel):
    """Flight condition and angle-of-attack sweep for the low-order model."""

    model_config = ConfigDict(extra="forbid")

    altitude_m: float = Field(ge=0.0, le=11_000.0)
    speed_kmh: float = Field(ge=80.0, le=500.0)
    alpha_min_deg: float = Field(ge=-10.0, le=15.0)
    alpha_max_deg: float = Field(ge=-5.0, le=20.0)
    alpha_samples: int = Field(ge=5, le=81)

    @model_validator(mode="after")
    def alpha_sweep_is_increasing(self) -> "BwbAnalysisCondition":
        if self.alpha_min_deg >= self.alpha_max_deg:
            raise ValueError("alpha_min_deg must be less than alpha_max_deg")
        return self


class RapidAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1"]
    design: BwbV1Design
    condition: BwbAnalysisCondition


class RapidDomainCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    minimum: float
    maximum: float
    unit: str
    status: Literal["pass", "fail"]


class RapidDomainStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["in_domain", "out_of_domain"]
    checks: list[RapidDomainCheck]


class BwbGeometryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_area_m2: float = Field(gt=0)
    span_m: float = Field(gt=0)
    semi_span_m: float = Field(gt=0)
    aspect_ratio: float = Field(gt=0)
    mean_aerodynamic_chord_m: float = Field(gt=0)
    wetted_area_m2: float = Field(gt=0)
    taper_ratio: float = Field(gt=0, le=1)
    volume_proxy_m3: float = Field(gt=0)


class BwbAircraftPolar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpha_deg: list[float]
    cl: list[float]
    cd: list[float]
    ld: list[float]

    @model_validator(mode="after")
    def arrays_have_matching_lengths(self) -> "BwbAircraftPolar":
        lengths = {len(self.alpha_deg), len(self.cl), len(self.cd), len(self.ld)}
        if len(lengths) != 1 or not self.alpha_deg:
            raise ValueError("polar arrays must be non-empty and have matching lengths")
        return self


class BwbAnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reynolds_number: float = Field(gt=0)
    mach: float = Field(gt=0)
    cl_alpha_per_rad: float = Field(gt=0)
    cl_at_zero_alpha: float
    cd0: float = Field(gt=0)
    induced_drag_factor: float = Field(gt=0)
    max_ld: float
    alpha_at_max_ld_deg: float


class BwbAnalysisProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: Literal["clean-room-bwb-low-order"]
    model_version: Literal["1.0.0"]
    geometry_decoder_id: Literal["clean-room-bwb-loft"]
    geometry_decoder_version: Literal["1.0.0"]
    methodology: str
    scope: Literal["whole_aircraft_longitudinal_polar"]
    uses_external_weights: Literal[False]
    uses_mit_assets: Literal[False]


class RapidAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1"]
    design_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    domain_status: RapidDomainStatus
    geometry: BwbGeometryMetrics
    polar: BwbAircraftPolar
    summary: BwbAnalysisSummary
    warnings: list[str]
    provenance: BwbAnalysisProvenance
    fidelity: Literal["conceptual_low_order"]

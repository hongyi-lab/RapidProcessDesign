from itertools import pairwise
from typing import Annotated, Literal

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


MISSION_DEMO_NATIVE_GEOMETRY_KEYS = frozenset(
    {
        "fuselage_length_m",
        "fineness_ratio",
        "wing_span_m",
        "wing_area_m2",
        "wing_sweep_deg",
        "wing_taper_ratio",
        "wing_thickness_ratio",
        "tail_scale",
    }
)

MISSION_DEMO_REQUIRED_INPUT_KEYS = frozenset(
    {
        "required_range_km",
        "payload_mass_kg",
        "cruise_speed_kmh",
        "cruise_altitude_m",
        "max_fuel_mass_kg",
        "max_takeoff_mass_kg",
        "target_lift_to_drag",
    }
)


class MissionDemoVariableDefinition(BaseModel):
    """One native geometry or demo-only sizing search dimension."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)
    input_upper_bound: str | None = None

    @model_validator(mode="after")
    def range_is_increasing(self) -> "MissionDemoVariableDefinition":
        if self.minimum >= self.maximum:
            raise ValueError(f"search range for {self.key} must be increasing")
        return self


class MissionDemoOptimizerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["seeded_uniform_search"]
    seed: int
    iterations: int = Field(ge=1, le=100)
    evaluations_per_iteration: int = Field(ge=1, le=1000)
    constraint_penalty: float = Field(gt=0)


class MissionDemoMissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpha_min_deg: float = Field(ge=-10.0, le=15.0)
    alpha_max_deg: float = Field(ge=-5.0, le=20.0)
    alpha_samples: int = Field(ge=5, le=81)
    wing_areal_density_kg_m2: float = Field(gt=0)
    wetted_area_density_kg_m2: float = Field(gt=0)
    wing_span_penalty_kg_m: float = Field(ge=0)
    systems_base_mass_kg: float = Field(ge=0)
    systems_payload_fraction: float = Field(ge=0)
    propulsion_mass_per_unit_kg: float = Field(ge=0)
    landing_gear_fraction: float = Field(ge=0, lt=1)
    reserve_fuel_fraction: float = Field(ge=0, lt=1)
    equivalent_tsfc_per_second: float = Field(gt=0)

    @model_validator(mode="after")
    def alpha_sweep_is_increasing(self) -> "MissionDemoMissionModel":
        if self.alpha_min_deg >= self.alpha_max_deg:
            raise ValueError("mission demo alpha sweep must be increasing")
        return self


class MissionDemoMetricCoverageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    status: Literal["connected", "partial", "not_connected"]
    source: str
    reason: str
    used_in_score: bool

    @model_validator(mode="after")
    def disconnected_metrics_are_never_scored(self) -> "MissionDemoMetricCoverageItem":
        if self.status == "not_connected" and self.used_in_score:
            raise ValueError(f"not-connected metric {self.key} cannot enter the score")
        return self


class MissionDemoMetricCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[MissionDemoMetricCoverageItem] = Field(min_length=1)

    @model_validator(mode="after")
    def metric_keys_are_unique(self) -> "MissionDemoMetricCoverage":
        keys = [metric.key for metric in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("mission demo metric coverage keys must be unique")
        return self


class MissionDemoProfile(BaseModel):
    """Versioned and explicitly non-formal mission search profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    profile_id: Literal["mission_demo_v1"]
    profile_version: str
    mode: Literal["demo_only"]
    formal_status: Literal["pending_teacher_decision"]
    title: str
    description: str
    disclaimer: str
    supported_family_ids: list[Literal["conventional_v2"]] = Field(min_length=1)
    candidate_count: int = Field(ge=3, le=10)
    diversity_threshold: float = Field(gt=0, le=1)
    inputs: list[RapidInputDefinition] = Field(min_length=1)
    geometry_variables: list[MissionDemoVariableDefinition] = Field(min_length=1)
    sizing_variables: list[MissionDemoVariableDefinition] = Field(min_length=1)
    optimizer: MissionDemoOptimizerConfig
    mission_model: MissionDemoMissionModel
    metric_coverage: MissionDemoMetricCoverage

    @model_validator(mode="after")
    def profile_contract_is_coherent(self) -> "MissionDemoProfile":
        if self.supported_family_ids != ["conventional_v2"]:
            raise ValueError("mission_demo_v1 supports only conventional_v2")
        geometry_keys = [variable.key for variable in self.geometry_variables]
        if len(geometry_keys) != len(set(geometry_keys)):
            raise ValueError("mission demo geometry variable keys must be unique")
        unknown_geometry = set(geometry_keys) - MISSION_DEMO_NATIVE_GEOMETRY_KEYS
        if unknown_geometry:
            raise ValueError(
                "mission demo geometry variables must be native ConventionalV2Design "
                f"fields: {', '.join(sorted(unknown_geometry))}"
            )
        sizing_keys = [variable.key for variable in self.sizing_variables]
        if sizing_keys != ["fuel_mass_kg"]:
            raise ValueError("mission_demo_v1 supports only fuel_mass_kg sizing")
        input_keys = [item.key for item in self.inputs]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("mission demo input keys must be unique")
        if set(input_keys) != MISSION_DEMO_REQUIRED_INPUT_KEYS:
            missing = sorted(MISSION_DEMO_REQUIRED_INPUT_KEYS - set(input_keys))
            unexpected = sorted(set(input_keys) - MISSION_DEMO_REQUIRED_INPUT_KEYS)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ValueError(
                "mission_demo_v1 inputs must match the evaluator contract ("
                + "; ".join(details)
                + ")"
            )
        for variable in self.sizing_variables:
            if variable.input_upper_bound not in input_keys:
                raise ValueError(
                    f"unknown input upper bound for {variable.key}: "
                    f"{variable.input_upper_bound}"
                )
        evaluation_budget = (
            self.optimizer.iterations * self.optimizer.evaluations_per_iteration
        )
        if self.candidate_count > evaluation_budget:
            raise ValueError("candidate_count exceeds the demo evaluation budget")
        if not any(
            metric.status == "not_connected"
            for metric in self.metric_coverage.metrics
        ):
            raise ValueError("mission demo coverage must expose unsupported metrics")
        return self


class MissionDemoJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["demo"]
    family_id: str
    preset_id: str = Field(min_length=1)
    inputs: dict[str, float]


class MissionDemoJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float = Field(ge=0, le=1)
    stage: str
    error: str | None = None
    created_at: str
    updated_at: str
    mode: Literal["demo"]
    family_id: Literal["conventional_v2"]
    preset_id: str
    profile_id: Literal["mission_demo_v1"]
    profile_version: str
    formal_status: Literal["pending_teacher_decision"]


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


class ConventionalV2Design(BaseModel):
    """High-level controls expanded by the conventional-v2 geometry decoder."""

    model_config = ConfigDict(extra="forbid")

    fuselage_length_m: float = Field(ge=6.0, le=20.0)
    fineness_ratio: float = Field(ge=6.0, le=16.0)
    nose_length_ratio: float = Field(ge=0.08, le=0.28)
    cabin_fullness: float = Field(ge=0.65, le=1.25)
    tailcone_length_ratio: float = Field(ge=0.20, le=0.42)
    section_ovality: float = Field(ge=0.70, le=1.30)
    wing_span_m: float = Field(ge=8.0, le=30.0)
    wing_area_m2: float = Field(ge=12.0, le=55.0)
    wing_root_x_ratio: float = Field(ge=0.25, le=0.50)
    wing_vertical_ratio: float = Field(ge=-0.25, le=0.35)
    wing_sweep_deg: float = Field(ge=0.0, le=35.0)
    wing_taper_ratio: float = Field(ge=0.20, le=0.60)
    wing_dihedral_deg: float = Field(ge=0.0, le=9.0)
    wing_twist_tip_deg: float = Field(ge=-6.0, le=2.0)
    wing_thickness_ratio: float = Field(ge=0.08, le=0.18)
    tail_arm_ratio: float = Field(ge=0.65, le=0.90)
    tail_scale: float = Field(ge=0.65, le=1.40)


class RapidAnalyzeRequest(BaseModel):
    """Family-neutral analyze request.

    ``design`` may contain a full vector or only overrides for ``preset_id``.
    The selected family owns its strict design validation in the registry.
    """

    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1", "conventional_v2"]
    preset_id: str | None = None
    design: dict[str, float] = Field(default_factory=dict)
    condition: BwbAnalysisCondition


class BwbAnalyzeRequest(BaseModel):
    """Strict request used internally by the BWB family adapter."""

    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1"]
    preset_id: str | None = None
    design: BwbV1Design
    condition: BwbAnalysisCondition


class ConventionalV2AnalyzeRequest(BaseModel):
    """Strict request used internally by the conventional-v2 adapter."""

    model_config = ConfigDict(extra="forbid")

    family_id: Literal["conventional_v2"]
    preset_id: str
    design: ConventionalV2Design
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


class GeometryCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["pass", "fail"]
    message: str


class LoftBodyStation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_m: float
    width_m: float = Field(ge=0)
    height_m: float = Field(ge=0)
    z_offset_m: float = 0.0
    shape_exponent: float = Field(default=2.0, ge=1.5, le=6.0)


class LoftBodyComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["loft_body"]
    stations: list[LoftBodyStation] = Field(min_length=2)

    @model_validator(mode="after")
    def stations_are_ordered(self) -> "LoftBodyComponent":
        coordinates = [station.x_m for station in self.stations]
        if any(after <= before for before, after in pairwise(coordinates)):
            raise ValueError("loft body station x coordinates must strictly increase")
        return self


class LiftingSurfaceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    y_m: float = Field(ge=0)
    leading_edge_x_m: float
    leading_edge_z_m: float
    chord_m: float = Field(gt=0)
    twist_deg: float = Field(ge=-15, le=15)
    # Large cant angles support V-tail and canted-fin surfaces as well as wings.
    dihedral_deg: float = Field(ge=-75, le=75)
    thickness_ratio: float = Field(gt=0.03, le=0.25)
    airfoil_id: str
    camber_ratio: float | None = Field(default=None, ge=0.0, le=0.12)
    camber_position_ratio: float | None = Field(default=None, gt=0.05, lt=0.95)
    interpolation_to_next: Literal["smooth", "linear"] = "smooth"


class LiftingSurfaceComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["lifting_surface"]
    symmetry: Literal["none", "y"]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    centerline_y_m: float = 0.0
    sections: list[LiftingSurfaceSection] = Field(min_length=2)

    @model_validator(mode="after")
    def sections_are_ordered(self) -> "LiftingSurfaceComponent":
        coordinates = [section.y_m for section in self.sections]
        if any(after <= before for before, after in pairwise(coordinates)):
            raise ValueError("lifting-surface section coordinates must strictly increase")
        return self


class NacelleStation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_m: float
    radius_y_m: float = Field(ge=0)
    radius_z_m: float = Field(ge=0)
    z_offset_m: float = 0.0


class NacelleComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["nacelle"]
    symmetry: Literal["none", "y"] = "none"
    centerline_y_m: float = Field(ge=0)
    stations: list[NacelleStation] = Field(min_length=2)

    @model_validator(mode="after")
    def stations_are_ordered(self) -> "NacelleComponent":
        coordinates = [station.x_m for station in self.stations]
        if any(after <= before for before, after in pairwise(coordinates)):
            raise ValueError("nacelle station x coordinates must strictly increase")
        return self


class PropellerComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["propeller"]
    symmetry: Literal["none", "y"] = "none"
    center_x_m: float
    centerline_y_m: float = Field(ge=0)
    center_z_m: float
    radius_m: float = Field(gt=0)
    hub_radius_m: float = Field(gt=0)
    hub_length_m: float = Field(gt=0)
    blade_count: int = Field(ge=2, le=8)
    blade_chord_m: float = Field(gt=0)
    rotation_deg: float = 0.0

    @model_validator(mode="after")
    def hub_and_blade_fit_inside_disk(self) -> "PropellerComponent":
        if self.hub_radius_m >= self.radius_m:
            raise ValueError("propeller hub radius must be smaller than disk radius")
        if self.blade_chord_m >= self.radius_m:
            raise ValueError("propeller blade chord must be smaller than disk radius")
        return self


GeometryComponent = Annotated[
    LoftBodyComponent | LiftingSurfaceComponent | NacelleComponent | PropellerComponent,
    Field(discriminator="kind"),
]


class GeometryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decoder_id: str
    decoder_version: str
    methodology: str
    archetype_id: str | None = None
    reference_basis: list[str] = Field(default_factory=list)


class GeometryState(BaseModel):
    """Canonical family-neutral geometry consumed by renderers and exporters."""

    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1", "conventional_v2"]
    geometry_version: str
    components: list[GeometryComponent] = Field(min_length=1)
    derived_metrics: dict[str, float]
    geometry_status: Literal["valid", "invalid"]
    geometry_checks: list[GeometryCheck]
    provenance: GeometryProvenance


class RapidAircraftPolar(BwbAircraftPolar):
    """Family-neutral name for the common longitudinal polar contract."""


class RapidAnalysisSummary(BwbAnalysisSummary):
    """Current common conceptual-analysis summary."""


class RapidAnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    polar: RapidAircraftPolar
    summary: RapidAnalysisSummary


class RapidAnalysisProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_version: str
    geometry_decoder_id: str
    geometry_decoder_version: str
    methodology: str
    scope: str
    uses_external_weights: bool
    uses_mit_assets: bool


class RapidAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1", "conventional_v2"]
    preset_id: str | None = None
    design_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_state: GeometryState
    geometry_metrics: dict[str, float]
    analysis: RapidAnalysisPayload
    domain_status: RapidDomainStatus
    warnings: list[str]
    provenance: RapidAnalysisProvenance
    fidelity: Literal["conceptual_low_order"]

    # Temporary aliases keep the released BWB client and regression suite
    # functional during the Round-4 frontend migration.
    geometry: dict[str, float]
    polar: BwbAircraftPolar
    summary: BwbAnalysisSummary


class RapidParameterDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)
    default: float
    group: Literal["geometry", "flight_condition"]

    @model_validator(mode="after")
    def default_is_in_range(self) -> "RapidParameterDefinition":
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError(f"default for {self.key} is outside its range")
        return self


class RapidFamilyPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset_id: str
    label: str
    description: str
    design: dict[str, float]
    archetype_id: str | None = None
    reference_basis: dict[str, str | float] | None = None


class RapidFamilyCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: bool
    analyze: bool
    optimize: bool


class RapidFamilyAnalysisInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    fidelity: Literal["conceptual_low_order"]
    description: str


class RapidFamilyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: Literal["bwb_v1", "conventional_v2"]
    display_name: str
    description: str
    version: str
    default_preset_id: str
    presets: list[RapidFamilyPreset] = Field(min_length=1)
    design_parameters: list[RapidParameterDefinition] = Field(min_length=1)
    condition_parameters: list[RapidParameterDefinition] = Field(min_length=1)
    capabilities: RapidFamilyCapabilities
    analysis: RapidFamilyAnalysisInfo
    optimization_status: Literal["pending_teacher_decision"]


class RapidFamiliesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    families: list[RapidFamilyManifest]

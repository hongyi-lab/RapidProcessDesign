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

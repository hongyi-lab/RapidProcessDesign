import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

from services.api.app.schemas.rapid_design import MissionDemoProfile, RapidDesignConfig

PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "rapid_design" / "demo.yaml"
MISSION_DEMO_PROFILE_PATH = (
    PROJECT_ROOT / "configs" / "rapid_design" / "mission_demo_v1.yaml"
)


@lru_cache(maxsize=4)
def load_rapid_design_config(path: str | None = None) -> RapidDesignConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return RapidDesignConfig.model_validate(payload)


@lru_cache(maxsize=4)
def load_mission_demo_profile(path: str | None = None) -> MissionDemoProfile:
    profile_path = Path(path) if path else MISSION_DEMO_PROFILE_PATH
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    return MissionDemoProfile.model_validate(payload)


def mission_demo_profile_hash(profile: MissionDemoProfile) -> str:
    canonical = json.dumps(
        profile.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validated_inputs(config: RapidDesignConfig, supplied: dict[str, float]) -> dict[str, float]:
    definitions = {item.key: item for item in config.inputs}
    unknown = sorted(set(supplied) - set(definitions))
    if unknown:
        raise ValueError(f"unknown inputs: {', '.join(unknown)}")

    values: dict[str, float] = {}
    for key, definition in definitions.items():
        value = float(supplied.get(key, definition.default))
        if not definition.minimum <= value <= definition.maximum:
            raise ValueError(
                f"{key} must be between {definition.minimum:g} and {definition.maximum:g}"
            )
        values[key] = value
    return values


def validated_mission_demo_inputs(
    profile: MissionDemoProfile,
    supplied: dict[str, float],
) -> dict[str, float]:
    definitions = {item.key: item for item in profile.inputs}
    unknown = sorted(set(supplied) - set(definitions))
    if unknown:
        raise ValueError(f"unknown mission demo inputs: {', '.join(unknown)}")

    values: dict[str, float] = {}
    for key, definition in definitions.items():
        value = float(supplied.get(key, definition.default))
        if not definition.minimum <= value <= definition.maximum:
            raise ValueError(
                f"{key} must be between {definition.minimum:g} and "
                f"{definition.maximum:g}"
            )
        values[key] = value
    return values

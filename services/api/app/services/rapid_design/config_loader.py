from functools import lru_cache
from pathlib import Path

import yaml

from services.api.app.schemas.rapid_design import RapidDesignConfig

PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "rapid_design" / "demo.yaml"


@lru_cache(maxsize=4)
def load_rapid_design_config(path: str | None = None) -> RapidDesignConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return RapidDesignConfig.model_validate(payload)


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

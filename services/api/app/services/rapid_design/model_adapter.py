from dataclasses import dataclass
from importlib.metadata import version
from math import pi

import numpy as np

from services.api.app.schemas.rapid_design import RapidAerodynamicsConfig


@dataclass(frozen=True)
class AirfoilOperatingPoint:
    alpha_deg: float
    lift_coefficient: float
    profile_drag_coefficient: float
    moment_coefficient: float
    max_lift_coefficient: float
    analysis_confidence: float
    reynolds_number: float


def naca4_coordinates(
    camber: float,
    camber_position: float,
    thickness: float,
    points_per_side: int = 60,
) -> np.ndarray:
    """Return normalized NACA four-digit-like coordinates, TE-upper to TE-lower."""
    beta = np.linspace(0.0, pi, points_per_side)
    x = 0.5 * (1.0 - np.cos(beta))
    yt = (
        5.0
        * thickness
        * (
            0.2969 * np.sqrt(np.maximum(x, 1e-12))
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1015 * x**4
        )
    )

    if camber <= 1e-8:
        yc = np.zeros_like(x)
        dyc_dx = np.zeros_like(x)
    else:
        p = float(np.clip(camber_position, 0.05, 0.95))
        fore = x < p
        yc = np.where(
            fore,
            camber / p**2 * (2.0 * p * x - x**2),
            camber / (1.0 - p) ** 2 * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2),
        )
        dyc_dx = np.where(
            fore,
            2.0 * camber / p**2 * (p - x),
            2.0 * camber / (1.0 - p) ** 2 * (p - x),
        )

    theta = np.arctan(dyc_dx)
    upper_x = x - yt * np.sin(theta)
    upper_y = yc + yt * np.cos(theta)
    lower_x = x + yt * np.sin(theta)
    lower_y = yc - yt * np.cos(theta)
    return np.vstack(
        (
            np.concatenate((upper_x[::-1], lower_x[1:])),
            np.concatenate((upper_y[::-1], lower_y[1:])),
        )
    )


class AerodynamicModelAdapter:
    def __init__(self, config: RapidAerodynamicsConfig):
        self.config = config

    @property
    def provenance(self) -> dict[str, object]:
        if self.config.backend == "neuralfoil":
            return {
                "name": "NeuralFoil",
                "version": version("neuralfoil"),
                "model_size": self.config.model_size,
                "license": "MIT",
                "paper": "NeuralFoil: An Airfoil Aerodynamics Analysis Tool Using Physics-Informed Machine Learning",
                "paper_url": "https://arxiv.org/abs/2503.16323",
                "repository_url": "https://github.com/peterdsharpe/NeuralFoil",
                "role": "2D airfoil CL/CD/CM and analysis-confidence surrogate",
            }
        return {
            "name": "analytic-test-model",
            "version": "1",
            "license": "project-internal",
            "role": "deterministic thin-airfoil approximation for tests only",
        }

    def evaluate(
        self,
        *,
        camber: float,
        camber_position: float,
        thickness: float,
        reynolds_number: float,
        required_lift_coefficient: float,
    ) -> AirfoilOperatingPoint:
        alpha = np.linspace(
            self.config.alpha_min_deg,
            self.config.alpha_max_deg,
            self.config.alpha_samples,
        )
        if self.config.backend == "neuralfoil":
            import neuralfoil as nf

            coordinates = naca4_coordinates(camber, camber_position, thickness)
            raw = nf.get_aero_from_coordinates(
                coordinates,
                alpha=alpha,
                Re=max(50_000.0, reynolds_number),
                model_size=self.config.model_size,
            )
            lift = np.asarray(raw["CL"], dtype=float).reshape(-1)
            drag = np.asarray(raw["CD"], dtype=float).reshape(-1)
            moment = np.asarray(raw["CM"], dtype=float).reshape(-1)
            confidence = np.asarray(raw["analysis_confidence"], dtype=float).reshape(-1)
        else:
            alpha_rad = np.deg2rad(alpha)
            lift = 2.0 * pi * (alpha_rad + 1.8 * camber)
            lift = np.clip(lift, -0.8, 1.65 - 0.8 * abs(thickness - 0.12))
            drag = 0.0075 + 0.008 * lift**2 + 0.08 * (thickness - 0.12) ** 2
            moment = np.full_like(lift, -0.55 * camber)
            confidence = np.full_like(lift, 0.92)

        finite = np.isfinite(lift) & np.isfinite(drag) & np.isfinite(confidence)
        if not np.any(finite):
            raise ValueError("aerodynamic surrogate returned no finite operating points")

        alpha = alpha[finite]
        lift = lift[finite]
        drag = drag[finite]
        moment = moment[finite]
        confidence = confidence[finite]
        order = np.argsort(lift)
        lift_sorted = lift[order]
        target = float(np.clip(required_lift_coefficient, lift_sorted[0], lift_sorted[-1]))
        alpha_value = float(np.interp(target, lift_sorted, alpha[order]))
        drag_value = float(np.interp(target, lift_sorted, drag[order]))
        moment_value = float(np.interp(target, lift_sorted, moment[order]))
        confidence_value = float(np.interp(target, lift_sorted, confidence[order]))

        return AirfoilOperatingPoint(
            alpha_deg=alpha_value,
            lift_coefficient=target,
            profile_drag_coefficient=max(0.001, drag_value),
            moment_coefficient=moment_value,
            max_lift_coefficient=float(np.max(lift)),
            analysis_confidence=float(np.clip(confidence_value, 0.0, 1.0)),
            reynolds_number=float(reynolds_number),
        )

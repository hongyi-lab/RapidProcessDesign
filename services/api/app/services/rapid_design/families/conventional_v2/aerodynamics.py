"""Canonical geometry -> AeroSandbox AeroBuildup + pretrained NeuralFoil.

This is a component-buildup model, not a wake-resolved solver or CFD. The
section profile matches geometrySurfaces.ts (camber plus closed-TE thickness).
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.metadata import version

import aerosandbox as asb
import numpy as np

from services.api.app.schemas.rapid_design import BwbAnalysisCondition, GeometryState

MODEL_ID = "neuralfoil-aerosandbox-buildup"
MODEL_VERSION = "1.0.0"
MODEL_SIZE = "small"
MIN_CONFIDENCE = 0.80
SOFTWARE_VERSIONS = {name: version(name) for name in ("neuralfoil", "aerosandbox")}


def section_coordinates(thickness: float, camber: float, position: float) -> np.ndarray:
    """Use the same vertical-thickness convention as the preview/export surface."""
    x = (1 - np.cos(np.linspace(0, np.pi, 101))) / 2
    yt = 5 * thickness * (
        0.2969 * np.sqrt(x) - 0.126 * x - 0.3516 * x**2
        + 0.2843 * x**3 - 0.1036 * x**4
    )
    yc = np.where(
        x < position,
        camber / position**2 * (2 * position * x - x**2),
        camber / (1 - position)**2 * (1 - 2 * position + 2 * position * x - x**2),
    )
    return np.concatenate([
        np.stack([x[::-1], (yc + yt)[::-1]], axis=1),
        np.stack([x[1:], (yc - yt)[1:]], axis=1),
    ])


@lru_cache(maxsize=256)
def _kulfan_parameters(thickness: float, camber: float, position: float) -> dict:
    foil = asb.Airfoil(
        name="canonical-section",
        coordinates=section_coordinates(thickness, camber, position),
    ).to_kulfan_airfoil()
    return {
        "lower_weights": foil.lower_weights,
        "upper_weights": foil.upper_weights,
        "leading_edge_weight": foil.leading_edge_weight,
        "TE_thickness": foil.TE_thickness,
    }


class _TrackedAirfoil(asb.KulfanAirfoil):
    def __init__(self, section, confidence_samples: list):
        match = re.search(r"naca\s*(\d)(\d)\d{2}", section.airfoil_id, re.IGNORECASE)
        camber = section.camber_ratio
        position = section.camber_position_ratio
        if camber is None:
            camber = int(match[1]) / 100 if match else 0.0
        if position is None:
            position = (int(match[2]) / 10 or 0.4) if match else 0.4
        super().__init__(
            name=section.airfoil_id,
            **_kulfan_parameters(section.thickness_ratio, camber, position),
        )
        self.confidence_samples = confidence_samples

    def get_aero_from_neuralfoil(self, *args, **kwargs):
        result = super().get_aero_from_neuralfoil(*args, **kwargs)
        self.confidence_samples.append(result["analysis_confidence"])
        return result


class AircraftAerodynamics:
    """One request-local aircraft; mutable controls are never shared between jobs."""

    def __init__(self, geometry: GeometryState, condition: BwbAnalysisCondition):
        self.condition = condition
        self.confidence_samples: list = []
        self.elevators: list = []
        wings = []
        bodies = []
        for component in geometry.components:
            if component.kind == "lifting_surface":
                # Pylons are included as lifting surfaces, but are not tail controls.
                controlled = component.id in {"v_tail", "t_tailplane", "utility_tailplane"}
                sections = []
                for section in component.sections:
                    controls = []
                    if controlled:
                        control = asb.ControlSurface(
                            name="elevator", symmetric=True, hinge_point=0.75, deflection=0.0,
                        )
                        controls.append(control)
                        self.elevators.append(control)
                    sections.append(asb.WingXSec(
                        xyz_le=[
                            section.leading_edge_x_m,
                            component.centerline_y_m + (
                                0.0 if component.orientation == "vertical" else section.y_m
                            ),
                            section.leading_edge_z_m,
                        ],
                        chord=section.chord_m,
                        twist=section.twist_deg,
                        airfoil=_TrackedAirfoil(section, self.confidence_samples),
                        control_surfaces=controls,
                    ))
                wings.append(asb.Wing(
                    name=component.id, symmetric=component.symmetry == "y", xsecs=sections,
                ))
            elif component.kind in {"loft_body", "nacelle"}:
                # Fairing lofts overlap the main body: do not double-count their volume/drag.
                if component.kind == "loft_body" and component.id != "fuselage":
                    continue
                nacelle = component.kind == "nacelle"
                offsets = [component.centerline_y_m] if nacelle else [0.0]
                if nacelle and component.symmetry == "y":
                    offsets.append(-component.centerline_y_m)
                for offset in offsets:
                    bodies.append(asb.Fuselage(name=component.id, xsecs=[
                        asb.FuselageXSec(
                            xyz_c=[s.x_m, offset, s.z_offset_m],
                            width=2 * s.radius_y_m if nacelle else s.width_m,
                            height=2 * s.radius_z_m if nacelle else s.height_m,
                            shape=2.0 if nacelle else s.shape_exponent,
                        ) for s in component.stations
                    ]))
        main_wing = next(wing for wing in wings if wing.name == "main_wing")
        self.reference = np.asarray(main_wing.aerodynamic_center(), dtype=float)
        self.reference[1] = 0.0
        self.chord = float(main_wing.mean_aerodynamic_chord())
        self.area = geometry.derived_metrics["reference_area_m2"]
        self.airplane = asb.Airplane(
            name="conventional_v2", wings=wings, fuselages=bodies,
            xyz_ref=self.reference.tolist(), s_ref=self.area, c_ref=self.chord,
            b_ref=geometry.derived_metrics["span_m"],
        )
        self.atmosphere = asb.Atmosphere(altitude=condition.altitude_m)

    def evaluate(self, alpha, elevator=0.0, *, cg_mac_fraction=0.25) -> dict[str, np.ndarray]:
        alpha, elevator = np.broadcast_arrays(
            np.atleast_1d(np.asarray(alpha, dtype=float)),
            np.atleast_1d(np.asarray(elevator, dtype=float)),
        )
        for control in self.elevators:
            control.deflection = elevator
        self.confidence_samples.clear()
        reference = self.reference.copy()
        reference[0] += (cg_mac_fraction - 0.25) * self.chord
        point = asb.OperatingPoint(
            atmosphere=self.atmosphere, velocity=self.condition.speed_kmh / 3.6,
            alpha=alpha,
        )
        aero = asb.AeroBuildup(
            airplane=self.airplane, op_point=point, xyz_ref=reference.tolist(),
            model_size=MODEL_SIZE,
        ).run()
        q_s = point.dynamic_pressure() * self.area
        result = {key.lower(): np.broadcast_to(np.asarray(aero[key]), alpha.shape)
                  for key in ("CL", "CD", "Cm")}
        result["cd_profile"] = np.asarray(aero["D_profile"]) / q_s
        result["cd_induced"] = np.asarray(aero["D_induced"]) / q_s
        result["confidence"] = np.min(np.stack([
            np.broadcast_to(np.asarray(value), alpha.shape)
            for value in self.confidence_samples
        ]), axis=0)
        if not all(np.isfinite(value).all() for value in result.values()):
            raise ValueError("AeroSandbox/NeuralFoil returned non-finite aerodynamics")
        if np.any(result["cd"] <= 0):
            raise ValueError("AeroSandbox/NeuralFoil returned non-positive drag")
        return result

    def trim(self, masses_kg, *, cg_mac_fraction=0.25, elevator_limit_deg=25.0) -> list[dict]:
        """Simultaneously solve L=W and Cm=0 at several cruise masses.

        Bounded Newton steps use batched finite differences of the actual model,
        not a sorted-CL interpolation that might cross a stalled branch.
        """
        masses = np.atleast_1d(np.asarray(masses_kg, dtype=float))
        q = 0.5 * float(self.atmosphere.density()) * (self.condition.speed_kmh / 3.6)**2
        required_cl = masses * 9.80665 / (q * self.area)
        alpha = np.full(masses.shape, 2.0)
        elevator = np.zeros(masses.shape)
        n = len(masses)
        h = 0.05
        alpha_min = max(-6.0, self.condition.alpha_min_deg)
        alpha_max = min(12.0, self.condition.alpha_max_deg)
        for _ in range(8):
            aero = self.evaluate(
                np.concatenate([alpha, alpha + h, alpha]),
                np.concatenate([elevator, elevator, elevator + h]),
                cg_mac_fraction=cg_mac_fraction,
            )
            cl, cm = aero["cl"][:n], aero["cm"][:n]
            cl_a = (aero["cl"][n:2*n] - cl) / h
            cm_a = (aero["cm"][n:2*n] - cm) / h
            cl_e = (aero["cl"][2*n:] - cl) / h
            cm_e = (aero["cm"][2*n:] - cm) / h
            converged = (np.abs(cl - required_cl) < 2e-4) & (np.abs(cm) < 2e-4)
            if np.all(converged):
                break
            determinant = cl_a * cm_e - cl_e * cm_a
            safe = np.where(np.abs(determinant) > 1e-9, determinant, np.inf)
            da = (cm_e * (required_cl - cl) + cl_e * cm) / safe
            de = (-cm_a * (required_cl - cl) - cl_a * cm) / safe
            alpha = np.clip(alpha + np.where(converged, 0, np.clip(da, -4, 4)),
                            alpha_min, alpha_max)
            elevator = np.clip(elevator + np.where(converged, 0, np.clip(de, -10, 10)),
                               -elevator_limit_deg, elevator_limit_deg)
        # Always evaluate the final iterate; the last Newton update may have hit a bound.
        final = self.evaluate(
            np.concatenate([alpha, alpha + h]), np.concatenate([elevator, elevator]),
            cg_mac_fraction=cg_mac_fraction,
        )
        points = []
        for i, mass in enumerate(masses):
            cl = float(final["cl"][i])
            cd = float(final["cd"][i])
            cm = float(final["cm"][i])
            cl_a = float((final["cl"][n+i] - cl) / np.radians(h))
            cm_a = float((final["cm"][n+i] - cm) / np.radians(h))
            converged = abs(cl - required_cl[i]) < 2e-4 and abs(cm) < 2e-4
            confidence = float(final["confidence"][i])
            attached = cl_a > 0.5  # Reject flat or descending lift branches.
            supported = bool(converged and attached and confidence >= MIN_CONFIDENCE)
            reason = "matched" if supported else (
                "low_model_confidence" if converged and confidence < MIN_CONFIDENCE
                else "stall_branch" if converged and not attached
                else "lift_not_supported" if abs(cl - required_cl[i]) >= 2e-4
                else "trim_not_supported"
            )
            points.append({
                "status": "supported" if supported else "unsupported", "reason_code": reason,
                "mass_kg": float(mass), "required_cl": float(required_cl[i]),
                "alpha_deg": float(alpha[i]), "elevator_deg": float(elevator[i]),
                "cl": cl, "cd": cd, "cm": cm, "ld": cl / cd,
                "lift_residual_n": float((cl - required_cl[i]) * q * self.area),
                "cl_alpha_per_rad": cl_a, "cm_alpha_per_rad": cm_a,
                "static_margin": -cm_a / cl_a if abs(cl_a) > 1e-9 else 0.0,
                "confidence": confidence, "drag_n": cd * q * self.area,
            })
        return points

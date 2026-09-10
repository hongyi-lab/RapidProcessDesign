"""Read-only resource audit; never trains, copies weights, or changes the reference repo.

Usage: python scripts/audit_bwb_resources.py --reference ../MIT/official_hackathon
Requires numpy and pandas. Output is an audit record, not aircraft validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/bwb-resource-audit.json"))
    args = parser.parse_args()
    ref = args.reference.resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ref / "models/ld_surrogate"))
    import predict_ld as predictor
    import flight_conversion as fc

    df = pd.read_csv(ref / "data/bwb_structures_dataset.csv")
    geom = {"B1/C1": .15, "B2/C1": .12, "B3/C1": .52, "C2/C1": .70,
            "C3/C1": .23, "C4/C1": .075, "S1": 50., "S3": 30.,
            "X3/C1": .575, "C1": 3000.}
    single = predictor.predict_ld(geom, 15., 180., 6.)
    batch = predictor.predict_ld_batch(pd.DataFrame([geom, geom]), 15., 180., 6.)
    geom_outside = predictor.predict_ld({**geom, "S3": 60.}, 15., 180., 6.)
    flight_outside = predictor.predict_ld(geom, 18., 250., 6.)
    fs1 = fc.convert(15., 180., 6., C1_mm=3000.)
    fs2 = fc.convert(15., 180., 6., C1_mm=4000.)
    features1 = np.asarray(fc.features_aero(geom, fs1))
    features2 = np.asarray(fc.features_aero({**geom, "C1": 4000.}, fs2))
    warnings_count = {}
    for _, row in df.iterrows():
        fs = fc.convert(row.Altitude, row.KCAS, row.AOA, row.C1)
        for warning in fc.check_ranges(fs):
            key = warning.split(" = ", 1)[0]
            warnings_count[key] = warnings_count.get(key, 0) + 1
    checkpoint_metadata = {}
    for tag in ("full", "feasible"):
        ck = json.loads((ref / f"models/ld_surrogate/reg_{tag}.json").read_text())
        checkpoint_metadata[tag] = {k: v for k, v in ck.items() if k not in ("model", "std")}
    inspected = ["README.md", "data/README.md", "data/bwb_structures_dataset.csv",
                 "models/ld_surrogate/README.md", "models/ld_surrogate/predict_ld.py",
                 "models/ld_surrogate/flight_conversion.py", "models/ld_surrogate/regressor.py",
                 "models/ld_surrogate/aero_design_space.json", "models/ld_surrogate/reg_full.json",
                 "models/ld_surrogate/reg_feasible.json", "ntop_model/README.md"]
    sha = {name: hashlib.sha256((ref / name).read_bytes()).hexdigest() for name in inspected}
    git = subprocess.run(["git", "-c", f"safe.directory={ref.as_posix()}", "-C", str(ref), "rev-parse", "HEAD"], capture_output=True, text=True)
    if git.returncode:
        raise RuntimeError(f"Cannot record reference commit: {git.stderr.strip()}")
    record = {
        "scope": "Resource/schema and inference smoke checks only; no aircraft validation",
        "reference_commit": git.stdout.strip(),
        "reference_files_sha256": sha,
        "dataset": {
            "shape": list(df.shape), "columns": list(df.columns),
            "all_numeric": all(pd.api.types.is_numeric_dtype(d) for d in df.dtypes),
            "all_finite": bool(np.isfinite(df.to_numpy()).all()),
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_input_rows": int(df.iloc[:, :24].duplicated().sum()),
            "min_max": {c: [float(df[c].min()), float(df[c].max())] for c in df},
            "stress_gt_335_MPa": int((df["Max Hotspot Stress"] > 335).sum()),
            "stress_gt_335p3_MPa": int((df["Max Hotspot Stress"] > 335.3).sum()),
            "stress_gt_1e4_MPa": int((df["Max Hotspot Stress"] > 1e4).sum()),
            "fuselage_rib_values": sorted(df["# of Fuselage Ribs"].unique().tolist()),
            "flight_warning_counts": warnings_count,
        },
        "checkpoint_metadata_reported_not_recomputed": checkpoint_metadata,
        "executed": {
            "single_example": single,
            "batch_abs_error_vs_single": float(np.max(np.abs(batch - single["LD"]))),
            "batch_match_at_1e_10_float_roundoff_tolerance": bool(np.allclose(batch, single["LD"], rtol=0, atol=1e-10)),
            "S3_60deg_outside_geometry_box": geom_outside,
            "alt18_kcas250_outside_flight_box": flight_outside,
            "C1_4000_over_3000_Re_ratio": fs2.Re_L / fs1.Re_L,
            "C1_only_changes_feature_indices": np.flatnonzero(features1 != features2).tolist(),
            "sea_level_CAS_equals_TAS_abs_error_ms": abs(fc.convert(0., 180., 0., 3000.).V_true - 180. * fc.KT_TO_MS),
        },
        "not_executed": ["held-out surrogate accuracy reproduction", "CFD", "FEA", "nTop execution",
                         "trim", "structural load mapping", "coupled aircraft solve", "mission integration", "optimization"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("reference_commit", "checkpoint_metadata_reported_not_recomputed", "executed")}, indent=2))
    print(json.dumps({k: v for k, v in record["dataset"].items() if k not in ("min_max", "columns")}, indent=2))
    print(f"Saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()

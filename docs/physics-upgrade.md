# NeuralFoil and trimmed cruise upgrade

The conventional aircraft family now uses pretrained NeuralFoil 0.3.3 through
AeroSandbox 4.2.10 AeroBuildup. The BWB family keeps its earlier conceptual model.
No hackathon geometry, datasets or model weights are copied into this project.

## What changed

- Section camber and thickness follow the same NACA-derived profile convention as
  the preview/STEP mesh. Section chords, twist, sweep, cant and tail positions feed
  the analysis. Vertical fins and mirrored nacelles use their canonical placement.
- AeroBuildup supplies component forces, moments and induced drag. It is a rapid
  three-dimensional component model, not a wake-resolved panel solver or RANS CFD.
- Analyze displays a neutral-elevator polar. Pitch moments are referenced to the
  main-wing quarter-chord aerodynamic center. Provenance and hashes include model
  versions and model size; saved results remain attributed to their original model.
- Design solves lift = weight and pitching moment = zero with bounded angle of
  attack/elevator at initial, midpoint and final cruise fuel masses. Confidence
  below 0.8 or a flat/descending lift branch cannot qualify as supported trim.
- Cruise requires at least 5% MAC longitudinal static margin and sufficient
  continuous shaft power at altitude. These conditions enter ranking/feasibility.
- Range integrates speed divided by fuel flow over usable fuel mass using Simpson's
  rule. Fuel flow uses required shaft power and BSFC. It never uses the untrimmed
  peak L/D. The L/D constraint uses the minimum at the three trimmed mass stations.
- Unsupported cruise reports range unavailable in the UI (numeric zero in the
  compatibility metric, with `cruise_supported=0` and the failure reason).

## Assumptions to calibrate with the supervisor

| Assumption | Initial value | Where to change |
| --- | --- | --- |
| CG, fixed throughout cruise | 25% of main-wing MAC | Advanced limits & assumptions |
| Sea-level rated shaft power | 180 kW per engine | Advanced limits & assumptions |
| Available continuous power | Rating × 0.85 × density / sea-level density | Mission profile |
| Propeller efficiency | 0.80 | Mission profile |
| Brake specific fuel consumption | 0.30 kg/kWh | Mission profile |
| Installed propulsion mass per engine | 52 kg + rating / 2.5 kW/kg | Mission profile |
| Elevator/ruddervator hinge and bounds | 75% chord; ±25° | Aero adapter / mission profile |
| Minimum static margin | 5% MAC, fixed-control derivative | Mission profile |

These are illustrative settings, not ratings for a selected real engine. Increasing
power also increases the mass estimate. The lapse rule approximates an unboosted
engine; turbocharged/turboprop installations need an appropriate engine map.
CG must later come from component placement and change with fuel/payload loading.
Wing/body/gear mass still uses the documented coefficient model.

The three cruise states assume constant speed, altitude and propeller efficiency.
Reserve fuel is retained. Climb/descent, takeoff/landing, wind, cooling/installational
drag corrections, propwash, thrust-line moments, wake/downwash coupling, dynamic
stability, deep stall, structural strength and aeroelasticity remain unvalidated or
unmodeled. A larger neural network would not resolve those omissions by itself.

## Verification

`tests/api/test_conventional_physics.py` contains repeatable checks for:

1. A symmetric AR=8 wing: zero-angle symmetry and small-angle lift agreement with
   an independent VLM calculation and the finite-wing analytical approximation
   (15% comparison tolerance). This checks basic behavior, not aircraft accuracy.
2. Actual camber/twist sensitivity and aft-CG changes to trim/static margin.
3. All three presets: lift residual below 5 N, |Cm| below 0.0002, bounded controls
   and sufficient model confidence at all three mass stations.
4. Low-power, aft-CG and low-speed/high-altitude failures: no supported range.
5. A constant-power analytical fuel/range case to check kW, kg/hour and km units.
6. Independence from untrimmed peak L/D and power-rating effects on propulsion mass.

The existing API, job recovery, deterministic search, public-session and frontend
tests also cover integration. Supervisor-approved aircraft cases, wind-tunnel or
CFD comparisons are still required before claiming engineering accuracy.

```bash
.venv/bin/python -m pytest tests/api/test_conventional_physics.py -q
```

On Windows use `.venv/Scripts/python.exe` instead. Public deployments install the
pinned packages in `requirements-demo.txt`; inference runs on CPU without a model
API key or runtime weight download. Container build downloads package dependencies.
The fixed 24-evaluation search budget is retained; search speed depends on the host.

## Upstream models

- [NeuralFoil source](https://github.com/peterdsharpe/NeuralFoil) and
  [paper](https://arxiv.org/abs/2503.16323): pretrained 2D airfoil model based on XFoil.
- [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox): finite-wing and body
  analysis with NeuralFoil sections. MIT-licensed libraries, with their own
  transitive dependency notices; see [third-party notices](../THIRD_PARTY_NOTICES.md).

## Updating the public demo

The Render service is configured for manual deployment. After this branch is
pushed, choose **Manual Deploy → Deploy latest commit** in the existing service.
New runs use profile version 2.0.0 and model `neuralfoil-aerosandbox-buildup`.
Older saved runs retain their earlier model; regenerate to compare the new results.

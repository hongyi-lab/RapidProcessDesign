# Publish the browser demo on Render

The project demo is live at **[rapidprocessdesign.onrender.com](https://rapidprocessdesign.onrender.com/)**.
Use the steps below to publish another instance or review its configuration.

One **Free Web Service** runs the Next.js interface and Python analysis together.
Visitors open its HTTPS address, change mission inputs, generate concepts, inspect
geometry, and download STEP or STL files. They need no account, API key, or local
installation. Your computer can be off after deployment.

## Configure the service

In Render, select **New → Web Service**, connect the GitHub repository, and use:

| Render field | Value |
| --- | --- |
| Source Code | `hongyi-lab/RapidProcessDesign` |
| Name | `rapid-process-design` (or another available name) |
| Language / Runtime | **Docker** — change the auto-detected Python selection |
| Branch | `codex/round8-simple-design-flow` |
| Region | Singapore, or the nearest available region |
| Root Directory | Leave empty |
| Dockerfile Path | `./Dockerfile` (if shown) |
| Docker Build Context | `.` (if shown) |
| Instance Type | **Free — $0/month** |
| Environment Variables | None required |
| Health Check Path | `/health` (under Advanced, if shown) |
| Docker Command | Leave empty; the image provides its startup command |
| Auto-Deploy | Off initially; use Manual Deploy for reviewed updates |

Confirm the bottom bar shows **$0/month**, then select **Deploy web service**.
Wait for the build to finish and the service to show **Live**. Open the generated
`https://…onrender.com` address. The home page opens Design automatically.

`render.yaml` provides the same single-service setup if you prefer a Render
Blueprint. Do not create both a Blueprint service and a manual service for this demo.

## Verify and share

1. Generate an aircraft and switch among the proposed concepts.
2. Open **Inspect geometry**, adjust a dimension, and check the model updates.
3. Use **Export → Download STEP** and **Download STL** in a normal browser.
4. Paste the verified public URL into the repository README as **Try the online demo**
   and into the GitHub repository's About → Website field.

The project instance was first deployed from `96ebb50` and verified on 6 September
2026. Other Render deployments receive their own address.

## Free demo behavior

- Free services sleep after 15 minutes without traffic. The next visit can take
  about a minute to start. This does not depend on your computer being on.
- Browser history is isolated with an anonymous HttpOnly cookie. Clearing cookies
  starts a new history. Server sleep, restart, or redeployment can erase saved runs;
  download files you want to keep.
- One browser can have one generation running at a time; up to four runs can be
  queued across visitors. Extra submissions receive a retry message.
- This public entry point exposes Design and Analyze. The local AI workspace and
  legacy optimizer remain available in local installations.
- STEP contains faceted solids in millimeters, without a SolidWorks feature tree.
- Free service hours, build minutes, and bandwidth have quotas. This setup selects
  a Free instance and adds no database, disk, paid service, or model-provider key.
  Review Render's billing settings if you add a payment method or upgrade later.

See [Render Free instances](https://render.com/docs/free) and
[Docker deployment](https://render.com/docs/docker) for current platform details.

## Local container check (optional)

```bash
docker build -t rapid-process-design .
docker run --rm -p 10000:10000 -e RAPID_SECURE_COOKIES=false rapid-process-design
```

Open `http://localhost:10000`. The cookie override is for local HTTP only; the
cloud image defaults to Secure cookies for Render HTTPS. No local storage,
environment files, credentials, or generated models are included in the image.

## Physics model update

The current conventional model installs NeuralFoil 0.3.3 and AeroSandbox 4.2.10
from `requirements-demo.txt`. They run locally on the server CPU without an API
key; dependencies and pretrained weights are installed at image build time.
Generate a new run after deploying to use trimmed cruise and power checks.
See the [model assumptions and verification](physics-upgrade.md).

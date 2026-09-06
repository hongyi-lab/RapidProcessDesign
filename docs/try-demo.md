# Try the current demo

The latest demo is on [`codex/round8-simple-design-flow`](https://github.com/hongyi-lab/RapidProcessDesign/tree/codex/round8-simple-design-flow). Select this branch when downloading the repository; `main` currently contains an older version.

Design, Analyze, and STEP/STL export run locally without an LLM API key, OpenVSP, or SolidWorks. Install Git, Python 3.11 or newer, and Node.js 24 (the tested Node version). The first installation needs internet access for dependencies.

## Windows

Run these commands in PowerShell:

```powershell
git clone --branch codex/round8-simple-design-flow --single-branch https://github.com/hongyi-lab/RapidProcessDesign.git
cd RapidProcessDesign
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
npm.cmd --prefix apps/web install
.\Start-RapidDesign.cmd
```

The launcher builds the interface and opens [the local demo](http://localhost:3900/rapid-design). On later visits, double-click `Start-RapidDesign.cmd`; use `Stop-RapidDesign.cmd` to stop it. Each person runs their own copy on their own computer.

## macOS / Linux

```bash
git clone --branch codex/round8-simple-design-flow --single-branch https://github.com/hongyi-lab/RapidProcessDesign.git
cd RapidProcessDesign
python3 -m venv .venv
.venv/bin/python -m pip install -e .
npm --prefix apps/web install
CAD_BACKEND=fake .venv/bin/python -m uvicorn services.api.app.main:app --host 127.0.0.1 --port 8900
```

Keep that terminal open. In a second terminal, from the repository root:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8900 npm --prefix apps/web run dev
```

Open [the local demo](http://localhost:3900/rapid-design).

## What to try

1. Choose an aircraft type, enter the mission, and select **Generate aircraft**.
2. Switch among the proposed concepts and inspect the model in 3D, top, side, or front view.
3. Select **Inspect geometry** to adjust its dimensions in Analyze.
4. Select **Export → Download STEP / Download STL**. Files use millimeters; this initial STEP export retains faceted bodies without a SolidWorks feature tree.

Saved runs belong to the local installation. Older saved shapes show a prompt to generate again with the updated model. The AI workspace under More tools requires a separate model connection.

## Sharing

The GitHub repository is public, so anyone can download and run it. There is currently no hosted public demo URL. `localhost` always refers to the visitor's own computer; sending someone your localhost link does not share your running application.

A browser-only public experience needs a deployment that runs both the web interface and Python analysis service. GitHub Pages alone hosts static files and cannot run the current Python service. See the [GitHub Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

To publish that experience, follow the [single-service Render deployment guide](deploy-render.md). The repository includes a Dockerfile and a Free-plan configuration; a live URL still needs to be deployed and verified in the owner's Render account.

中文：体验最新版请下载上面的开发分支，安装 Python 和 Node.js 后按对应系统的步骤启动。Design、Analyze 和文件导出无需 API 密钥。仓库目前提供源码与本地运行方式，尚无免安装的在线体验网址。

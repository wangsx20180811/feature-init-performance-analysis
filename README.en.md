# CASE-Excel_merge

**Languages / 语言:** [中文（完整文档）](README.md) | **English (this file)**

A toolkit for **Excel merge, preview, TopN, and extended HR analytics**, plus a browser-based **HR web app** (upload spreadsheets after login; run analyses via forms or a simple prompt; download merged/exported results).

### About the “description” on GitHub’s file list

Each row in the GitHub repository’s file browser shows the **commit message of the most recent commit that touched that path** — not a separate per-file description stored in the repo. Different paths may therefore show different historical messages (e.g. “init” vs “deploy”). That is **expected**. To set the short blurb under the repo name, use **Settings → General → Repository description** on GitHub.

## Contents

- [Overview](#overview)
- [Directory layout](#directory-layout)
- [Requirements](#requirements)
- [Quick deploy & run](#quick-deploy--run)
- [Release tarball & Linux rollout](#release-tarball--linux-rollout)
- [Hot upgrade (keep data, recommended)](#hot-upgrade-keep-data-recommended)
- [ECS one-shot deploy (`scripts/deploy_ecs.sh`)](#ecs-one-shot-deploy-scriptsdeploy_ecssh)
- [Default login & password change](#default-login--password-change)
- [Docker (optional)](#docker-optional)
- [Stop the web service](#stop-the-web-service)
- [Disclaimer](#disclaimer)

> For full step-by-step details (Windows, CLI, Web UI, etc.), see the **[Chinese README](README.md)**.

---

## Overview

- **Web app** (`hr_excel_web/`): Flask; table A (employee master), multi-file performance data, optional `hr_config.json` mapping; form-driven or prompt-driven workflows.
- **Core logic** (`tools/`): read/filter, merge, TopN, extended analytics — used by the web app and `main.py` CLI.

## Directory layout

| Path | Role |
|------|------|
| `main.py` | Entry: no args or `web` starts the web UI; `merge` / `topn` / `ext` / `read` call `tools/` |
| `requirements.txt` | Python dependencies (pinned) |
| `deploy.bat` / `deploy.sh` | Create venv + `pip install` |
| `run_hr_web.*` | Start web and try to open a browser |
| `tools/` | Merge, read, perf loader, TopN, extended analytics, column mapper, … |
| `hr_excel_web/` | Flask app (`app.py`, templates, `uploads/`, `exports/`) |
| `package_release.sh` | Build `tar.gz` for release (excludes venv, uploads, …) |
| `scripts/deploy_ecs.sh` | **Production Linux**: systemd, venv, env file, health check, optional cleanup timer |
| `Dockerfile` | Optional container image |

## Requirements

- **Python 3.10–3.12** (wheels are referenced for 3.12 on Linux).
- **64-bit** OS recommended.

## Quick deploy & run

- **Windows:** Install Python 3.10+ (64-bit), run `deploy.bat`, then `run_hr_web.bat` or `venv\Scripts\python.exe main.py`.
- **Linux:** `chmod +x deploy.sh && ./deploy.sh`, `source venv/bin/activate`, `python main.py`. For LAN access: `export HR_WEB_HOST=0.0.0.0 HR_WEB_DEBUG=0`.

## Release tarball & Linux rollout

From the **project root** (Git Bash / Linux):

```bash
chmod +x package_release.sh
./package_release.sh
```

This writes **`CASE-Excel_merge_release_<timestamp>.tar.gz`** to the **parent directory** of the project (see `package_release.sh` excludes).

## Hot upgrade (keep data, recommended)

Once the service has run in production, **do not delete the whole deployment directory** before unpacking a new release. Prefer **overlaying** the new tree on the same path and re-running the deploy script so uploads, exports, `password_overrides.json`, etc. stay in place.

1. Upload the new **`CASE-Excel_merge_release_*.tar.gz`** to the server (e.g. next to the project or under `/root`).
2. **Extract from the parent directory of `CASE-Excel_merge`** so the archive’s top-level folder **`CASE-Excel_merge/`** merges into the existing folder:

```bash
cd /data/dev   # example: parent of CASE-Excel_merge; adjust to your path
tar -xzf /path/to/CASE-Excel_merge_release_xxxx.tar.gz
```

3. From the project root: **`sudo bash scripts/deploy_ecs.sh`** with defaults (do **not** set **`DEPLOY_CLEAN_DATA=1`** unless you intend to wipe data).

**Not recommended:** deleting the entire project folder before unpacking — you will lose **`uploads/`**, **`exports/`**, **`password_overrides.json`**, etc., unless you restore from backup.

If you deploy to a **new path** and move `WorkingDirectory` in systemd, **migrate** those directories manually.

## ECS one-shot deploy (`scripts/deploy_ecs.sh`)

On **Ubuntu + systemd** (typical for Alibaba Cloud ECS):

```bash
cd /path/to/CASE-Excel_merge
chmod +x deploy.sh run_hr_web.sh package_release.sh scripts/deploy_ecs.sh scripts/cleanup_web_temp.sh
sudo bash scripts/deploy_ecs.sh
```

Important environment variables (see script header for full list):

| Variable | Default | Notes |
|----------|---------|--------|
| `DEPLOY_CLEAN_DATA` | `0` | **`1` wipes uploads/exports/audit** — dangerous |
| `DEPLOY_PURGE_VENV` | `0` | `1` deletes and recreates `venv` |
| `DEPLOY_GENERATE_LOGIN_PASSWORDS` | `0` | `1` writes random `HR_WEB_PASSWORD_*` into env |

Use **`DEPLOY_PIP_INDEX_URL`** (e.g. Tsinghua mirror) on slow networks in China.

## Default login & password change

If **`HR_WEB_PASSWORD_*`** are **not** set in the environment file, the built-in rule is **password equals username** (e.g. `hr_admin` / `hr_admin`). After first login, users **must** set a new password via the web UI before accessing the workspace.

If env passwords are set, follow your server’s **`/etc/default/case-excel-web`** or **`/root/.case-excel-web.initial`**.

## Docker (optional)

```bash
docker build -t case-excel-merge:latest .
docker run -d -p 5001:5001 \
  -v "$(pwd)/hr_excel_web/uploads:/app/hr_excel_web/uploads" \
  -v "$(pwd)/hr_excel_web/exports:/app/hr_excel_web/exports" \
  case-excel-merge:latest
```

## Stop the web service

- **Foreground:** Ctrl+C.
- **systemd:** `sudo systemctl stop case-excel-web` (or your unit name).

## Disclaimer

This project is aimed at practical intranet use. For production, replace default secrets and accounts, disable debug, and use HTTPS and proper access control.

---

**Full documentation (Chinese):** [README.md](README.md)

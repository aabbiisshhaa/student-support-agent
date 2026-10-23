# Deployment Runbook

## Student-Support Case Agent v1.0.0

This runbook explains how to reproduce and operate the CLI and Streamlit Web UI locally or in Docker.

## 1. Prerequisites

Install:

- Git
- Python 3.12
- Docker Desktop with Docker Compose

Confirm Docker is running:

```powershell
docker --version
docker compose version
```

## 2. Environment Configuration

From the repository root, create the local environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure:

```text
GEMINI_API_KEY=your_real_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_MS=30000
MODEL_OFFLINE_MODE=false
DATABASE_URL=sqlite:///./student_support.db
MODEL_CONTEXT_LIMIT=1048576
TOKEN_WARNING_THRESHOLD=0.80
TELEMETRY_LOG_PATH=logs/telemetry.jsonl
```

Never commit `.env` or real API keys.

## 3. Online and Offline Modes

### Online mode

Online mode uses Gemini and requires a valid API key:

```text
MODEL_OFFLINE_MODE=false
GEMINI_API_KEY=your_real_key
```

### Deterministic offline mode

Offline mode disables Gemini initialization and uses the system’s deterministic fallback behaviour:

```text
MODEL_OFFLINE_MODE=true
```

A Gemini API key is not required while offline mode is enabled.

## 4. Local Python Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the pinned dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run all tests:

```powershell
python -m pytest -q
```

## 5. Run Locally

### CLI

```powershell
python src\app.py
```

Optional CLI arguments:

```powershell
python src\app.py --student-id 2300712345
python src\app.py --session YOUR_SESSION_TOKEN
python src\app.py --verbose
```

### Web UI

```powershell
streamlit run src\ui\app.py
```

Open:

```text
http://localhost:8501
```

## 6. Build Docker Images

Build the CLI and Web UI images:

```powershell
docker compose build
docker compose --profile cli build cli
```

The Dockerfile uses separate targets:

- `cli` for `src/app.py`
- `web` for `src/ui/app.py`

Both targets use the same pinned Python 3.12 environment.

## 7. Run with Docker Compose

### Web UI

```powershell
docker compose up web
```

Open:

```text
http://localhost:8501
```

Run in the background:

```powershell
docker compose up -d web
```

### Interactive CLI

```powershell
docker compose --profile cli run --rm cli
```

### Offline Web UI

Set this value in `.env`:

```text
MODEL_OFFLINE_MODE=true
```

Then run:

```powershell
docker compose up web
```

### Offline CLI

Set `MODEL_OFFLINE_MODE=true` in `.env`, then run:

```powershell
docker compose --profile cli run --rm cli
```

## 8. Ports and Persistent Data

| Component | Port or location |
|---|---|
| Streamlit Web UI | `8501` |
| Application data | Docker volume `agent-data` |
| Telemetry logs | Docker volume `agent-logs` |
| Execution traces | Docker volume `agent-traces` |

If port 8501 is already occupied, change the host side of the mapping in `docker-compose.yml`:

```yaml
ports:
  - "8502:8501"
```

The application would then be available at `http://localhost:8502`.

## 9. Operational Commands

View running containers:

```powershell
docker compose ps
```

View Web UI logs:

```powershell
docker compose logs -f web
```

Stop containers:

```powershell
docker compose down
```

Stop containers and remove the project volumes:

```powershell
docker compose down -v
```

The `-v` command permanently removes persisted application data, logs and traces. Use it only when deletion is intended.

## 10. Verification

Validate the Compose configuration:

```powershell
docker compose config
```

Run the test suite:

```powershell
python -m pytest -q
```

Build both application targets:

```powershell
docker compose build
docker compose --profile cli build cli
```

Check the Web UI health endpoint after startup:

```powershell
Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing
```

A healthy service returns an HTTP success response.

## 11. Troubleshooting

### Docker daemon unavailable

Start Docker Desktop and retry:

```powershell
docker info
```

### Missing `.env`

Create it from the supplied template:

```powershell
Copy-Item .env.example .env
```

### Invalid Gemini API key

Correct `GEMINI_API_KEY` in `.env`, or use:

```text
MODEL_OFFLINE_MODE=true
```

### Web UI does not open

Check container status and logs:

```powershell
docker compose ps
docker compose logs web
```

Confirm that port `8501` is not being used by another application.

### Dependency installation failure

Confirm Python 3.12 is being used and rebuild without cache:

```powershell
python --version
docker compose build --no-cache
```

### Rebuild after dependency changes

```powershell
docker compose build --no-cache
docker compose up web
```

## 12. Release Procedure

The `v1.0.0` tag must only be created after:

1. The complete test suite passes.
2. Both Docker targets build successfully.
3. The Web UI health check succeeds.
4. The deployment pull request is reviewed and merged into `main`.
5. The release commit on `main` is confirmed.

After merging:

```powershell
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

Create the GitHub release from tag `v1.0.0` and include the verified release notes and deployment instructions.

Do not move or recreate the tag after publication. Any later changes require a new semantic version.
# Dayweave AI

Dayweave is a local-first personal workspace with a React/Vite frontend, a FastAPI API, SQLite for local development, and PostgreSQL support for Docker and Render. The existing workspace UI is retained; a sign-in/register screen was added because the original starter had no authentication UI.

## Functionality and security audit

- **Authentication:** email/password registration and login; scrypt password hashes; seven-day random server-side sessions; HttpOnly cookies; CSRF token required on authenticated writes; logout revokes the current session; login failures are throttled by client IP.
- **Authorization:** tasks, sources, memories, focus sessions, activity, files, folders and AI workspace context are scoped to the authenticated user. Foreign resource identifiers return 404. Legacy memories without known ownership remain unassigned.
- **Persistence:** SQLite for local development, SQLAlchemy connection layer supporting PostgreSQL, and non-destructive schema creation/additive ownership-column migration at startup.
- **Security controls:** exact-origin CORS allowlist, origin validation on writes, generic login errors, request validation, upload size/type checks, security response headers, and no client-side auth token storage.
- **Current product workflows:** tasks, notes/sources, memories, dashboard, task calendar, focus session persistence, activity, JSON export, and optional cloud AI chat remain available after sign-in.
- **Inbox file manager:** user-owned folders and files support multi-file uploads, rename/move/delete, search, download, text/PDF/image previews, and per-file ownership checks. File bytes live in configurable persistent storage rather than the database.

The following requirements are not complete yet: versioned Alembic migrations, email verification/password reset, all-session revocation UI, reminders and durable workers, conversations/action approvals, semantic RAG, full calendar event CRUD, integrations, account deletion, object storage, and a full audit trail for every UI control. Do not treat this as a finished production SaaS yet.

## START / DEVELOP — Windows PowerShell

Install Node.js 20+, Python 3.11+, and (for Docker) Docker Desktop. In project terminal 1:

```powershell
cd "D:\projects\New folder\new"
npm.cmd install
npm.cmd run dev
```

In project terminal 2:

```powershell
cd "D:\projects\New folder\new\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs. Create your account from the sign-in screen. Local SQLite data is stored in `backend/dayweave.db`.

If PowerShell blocks activation, run the `pip` and `uvicorn` commands without activating the venv. Use `npm.cmd` if the `npm` PowerShell shim is blocked.

### Cloud AI (optional)

Configure a cloud provider from **Settings / AI Models**. Generate and set `AI_CREDENTIAL_ENCRYPTION_KEY` as shown in `.env.example` before starting the backend; the local API does not automatically load `.env`. Keep the key stable so saved provider credentials remain decryptable.

## START / DEVELOP — Docker Compose

Docker Desktop must be running. Compose uses the isolated project name `dayweave-ai`, its own network, the `dayweave-ai_postgres_data` volume, and a separate persistent `file_data` volume for uploaded bytes. PostgreSQL has no published host port. The UI and API host ports are configurable; `scripts/start-docker.ps1` checks for listeners and picks free alternatives without stopping anything already using a port.

```powershell
cd "D:\projects\New folder\new"
Copy-Item .env.example .env
notepad .env # change POSTGRES_PASSWORD before starting
.\scripts\start-docker.ps1
```

Before starting, set `AI_CREDENTIAL_ENCRYPTION_KEY` in `.env` if you plan to save cloud provider credentials. Generate a key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, then paste its output into `.env`. Keep `.env` private and keep the same key for future restarts/backups. Leave the value blank if you will not configure a cloud provider.

The script builds and starts only this Compose project and prints the selected frontend/API URLs. If Docker Desktop is unavailable, it exits without changing containers. You can also start manually after setting free ports in `.env`:

```powershell
docker compose --env-file .env -p dayweave-ai config
docker compose --env-file .env -p dayweave-ai up -d --build
```

Open the frontend URL (normally http://localhost:8080). The API is normally at http://localhost:8000; `/api/v1/health` checks database connectivity. Sign in or register in the app. Compose waits for PostgreSQL health, runs the Alembic migration before starting FastAPI, then waits for the API health check before starting Nginx.

### Inspect, logs, stop, restart, rebuild

These commands are scoped to the Dayweave project. They do not stop other Compose projects, and `down` preserves the named database and file volumes:

```powershell
docker compose -p dayweave-ai ps
docker compose -p dayweave-ai logs -f backend
docker compose -p dayweave-ai logs -f postgres
docker compose -p dayweave-ai logs -f frontend
docker compose -p dayweave-ai restart
docker compose -p dayweave-ai up -d --build
docker compose -p dayweave-ai down
```

Do not add `-v` to `down` if you need the database or uploaded files. The application intentionally does not publish the PostgreSQL port. If a host port conflict remains, edit `BACKEND_PORT` or `FRONTEND_PORT` in `.env` and run the project-scoped `up -d --build` command again.

### Database migration and backup

The container runs `alembic upgrade head` at startup. To apply it manually to the running Compose database:

```powershell
docker compose -p dayweave-ai exec backend alembic upgrade head
```

Create a plain SQL backup in the project directory:

```powershell
docker compose -p dayweave-ai exec -T postgres pg_dump -U dayweave -d dayweave > .\dayweave-backup.sql
```

Restore only into a new/empty database after verifying the backup and target. This does not drop existing tables, and can fail on duplicate records if used against a non-empty database:

```powershell
Get-Content -Raw .\dayweave-backup.sql | docker compose -p dayweave-ai exec -T postgres psql -U dayweave -d dayweave
```

### AI provider controls

After signing in, open **Settings → AI Models** to select OpenRouter, Groq, Google Gemini, xAI/Grok, OpenAI, Cerebras, Together AI, or a custom OpenAI-compatible provider. For a cloud provider, configure `AI_CREDENTIAL_ENCRYPTION_KEY` in `.env` before starting Docker, enter the provider API key in the masked field, click **Fetch Models**, search/filter the returned provider model IDs, select a model, click **Test Connection**, then click **Save Configuration**. Fetch and test requests are sent to the backend; fetching does not persist the key. Saved cloud credentials are encrypted at rest and never returned to the browser. Without a cloud key, AI chat reports that no provider is configured and other workspace features remain available. See [DOCKER_RUN.md](DOCKER_RUN.md) for the key generation command and step-by-step Windows Docker, backup, and troubleshooting instructions.

## Tests and builds

```powershell
# Frontend type-check and production bundle
npm.cmd run build

# Backend auth, CSRF, migration-preservation, session, tenant and AI-unavailable tests
python -m pip install -r backend\requirements-dev.txt
python -m pytest backend\tests -q

# Check the project-scoped Docker configuration (no containers are started)
docker compose --env-file .env.example -p dayweave-ai config --quiet
```

## Deploy to Render

The repository includes `render.yaml`, which defines separate Dockerized frontend and FastAPI services plus PostgreSQL. Render does not run this local Compose file as one service. Push the repository to a Git provider, create a Render Blueprint from it, and review each resource before applying. The Blueprint uses Render's free PostgreSQL plan to avoid silently selecting paid infrastructure. **Free Render Postgres expires after 30 days and is unsuitable for real user data; upgrade it to a paid plan before production use** ([Render free instance limits](https://render.com/docs/free)).

The Blueprint uses these runtime settings:

- `DATABASE_URL`: supplied from the Render PostgreSQL connection string.
- `ENVIRONMENT=production`: enables secure cookies and `SameSite=None` for the split frontend/API origins.
- `CORS_ALLOWED_ORIGINS=https://dayweave.onrender.com`: restricts browser access to the frontend domain.
- `SESSION_SECONDS=604800`: session lifetime (seven days).
- Frontend API URL: the Dockerfile build argument defaults to `https://dayweave-api.onrender.com`; Compose overrides it for the selected local backend port.

The names above are the Blueprint defaults. If you change the Render service names, update the `VITE_API_URL` build argument default in the root `Dockerfile`; if you add a custom frontend domain, update the API's `CORS_ALLOWED_ORIGINS` in Render. Never put database credentials or other secrets in `VITE_*` values. The API health check is `/api/v1/health`; it checks database connectivity without returning connection details. PostgreSQL changes use Alembic; local SQLite retains a non-destructive bootstrap for zero-setup development. Review and back up the database before deploying future schema changes.

Render deployment was not executed from this workspace. Docker Compose configuration parses, and an Alembic migration was tested against both a fresh SQLite database and a legacy SQLite schema while retaining its row. Container startup, PostgreSQL integration, and image builds could not be verified here because Docker Engine was not running. The Docker inventory commands also could not connect, so no existing container/network/volume inventory was available; no Docker container or volume command that modifies state was run.

File metadata is stored in PostgreSQL and local files use `backend/data/files`; Compose mounts a named `file_data` volume, and the Render blueprint mounts a persistent disk at `/var/data/dayweave-files`. Render persistent disks require a paid web service plan. Back up file storage together with the database. Existing memories without a trustworthy owner remain inaccessible instead of being assigned to a new account. A worker is not included because durable reminder/document processing jobs are not implemented. Alembic migrations are additive and deliberately preserve user data on downgrade.
#   D a y _ w a v e r _ a i  
 
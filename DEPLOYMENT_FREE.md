# Dayweave AI: Vercel + Render + Aiven deployment

## Architecture and repository layout

```
Vercel (Vite/React at repository root)
  -> Render (FastAPI in backend/)
    -> Aiven PostgreSQL
```

- Frontend root directory: the repository root (`.`); source is `src/` and the Vite output is `dist/`.
- Backend root directory: `backend/`; FastAPI entry point is `main:app` in `backend/main.py`.
- Render health endpoint: `/api/v1/health` (unauthenticated, checks database connectivity).
- The API is built from `backend/Dockerfile`; its command first runs `alembic upgrade head`, then starts Uvicorn on Render's `PORT`.

## Before deploying

1. Push this repository to `https://github.com/chvinne10/Day_waver_ai.git` without `.env`.
2. In Aiven, obtain the PostgreSQL service host, port, database, and password. URL-encode the password if it contains reserved URL characters.
3. Generate a production encryption key locally and store it only in Render:

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Do not rotate this key after users save AI provider credentials unless those credentials are migrated/re-entered.

## Render: backend

Create a **Web Service** from the GitHub repository, or create a Blueprint from `render.yaml`. The Blueprint intentionally creates only the API service; it does not create a Render database, frontend service, or paid disk.

Use these settings:

| Setting | Value |
| --- | --- |
| Name | `dayweave-api` (or your preferred name) |
| Runtime | Docker |
| Dockerfile path | `./backend/Dockerfile` |
| Docker build context | `./backend` |
| Health check path | `/api/v1/health` |
| Start command | Defined in the Dockerfile; do not override it |

Set these Render environment variables in the Dashboard:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://avnadmin:<URL_ENCODED_PASSWORD>@pg-279c642b-chvinaykumarchviti-9e65.e.aivencloud.com:26354/defaultdb?sslmode=require` |
| `ENVIRONMENT` | `production` |
| `CORS_ALLOWED_ORIGINS` | Exact Vercel origin, for example `https://your-project.vercel.app` |
| `SESSION_SECONDS` | `604800` |
| `AI_CREDENTIAL_ENCRYPTION_KEY` | New Fernet key generated above |
| `FILE_STORAGE_ROOT` | `/app/data/files` |

Never put the Aiven password, AI encryption key, or an AI provider key in Git, a Vercel variable, or a `VITE_` variable. `psycopg` v3 is installed and matches the `postgresql+psycopg://` scheme.

After the first deploy, request `https://<render-service>.onrender.com/api/v1/health`. It must return HTTP 200 and a JSON response with `status: "ok"`. A non-200 response normally means that `DATABASE_URL` is missing, malformed, blocked by Aiven's network policy, or migrations failed.

### Migrations

The Render container runs `alembic upgrade head` before Uvicorn starts. This is additive and does not recreate or drop the schema. To run it manually from a one-off Render shell, use:

```sh
cd /app && alembic upgrade head
```

Alembic reads `DATABASE_URL`, converts `postgres://` and `postgresql://` to the installed psycopg v3 dialect, and uses the original URL directly for the migration engine. This avoids ConfigParser misinterpreting percent-encoded password characters.

## Vercel: frontend

Import the same GitHub repository into Vercel. Configure:

| Setting | Value |
| --- | --- |
| Root Directory | `.` (repository root) |
| Framework | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

Add this Vercel production environment variable before deploying:

| Variable | Value |
| --- | --- |
| `VITE_API_URL` | `https://<render-service>.onrender.com` |

`VITE_API_URL` is baked into the frontend bundle, so redeploy Vercel after changing it. The frontend sends requests with credentials; the backend must use the exact Vercel HTTPS origin in `CORS_ALLOWED_ORIGINS`. Do not use `*` because credentialed CORS forbids it.

Vite's SPA fallback is handled by Vercel's Vite deployment behavior. If a custom rewrite is later needed, route all non-asset paths to `index.html`; do not proxy API routes through Vercel unless that design is deliberately adopted.

## Local variables

Copy `.env.example` to the ignored `.env` only for local development/Docker Compose. Docker Compose uses `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`; non-Docker FastAPI can use `DATABASE_URL` or local SQLite via `DAYWEAVE_DB`. Keep `AI_CREDENTIAL_ENCRYPTION_KEY` stable wherever saved cloud credentials exist.

## Verification checklist

1. Open the Vercel URL and register an account.
2. Reload the page; the authenticated session should persist. Log out and confirm protected pages require login again.
3. Create a task or note. Browser requests should include the Vercel origin and succeed without CORS errors.
4. In Settings > AI Models, enter a provider key, use **Fetch Models**, **Test Connection**, and then save. Keys are encrypted server-side with `AI_CREDENTIAL_ENCRYPTION_KEY`.
5. Upload, download, and preview a supported file. The metadata is in PostgreSQL.

## Storage and free-tier limitations

Render Free has an ephemeral filesystem. `/app/data/files` can be lost on a restart, redeploy, or service recycle, so uploaded file *bytes* are not durable even though their metadata remains in Aiven. This deployment does not pretend otherwise. A future safe migration is to an S3-compatible object store with a currently available free allowance (for example Cloudflare R2 only if its current plan and egress rules suit the account), while retaining `inbox_files.storage_key` as the object key.

Free plans and availability change. Before entering production data, verify the current limits directly in each provider dashboard: Render may cold-start/sleep or impose monthly usage limits; Vercel has plan-specific bandwidth/function limits; and Aiven availability, credits, storage, and service lifetime depend on the account/region. No paid Render disk or Render PostgreSQL resource is configured here.

## Common failures

| Symptom | Check |
| --- | --- |
| `Could not parse SQLAlchemy URL` during migration | Ensure `DATABASE_URL` is one line, password characters are URL-encoded, and it uses the psycopg form above. |
| Health endpoint returns 503 | Confirm Aiven host/port/database, SSL mode, password, service network access, and migration logs. |
| Browser CORS error or login fails | Set `CORS_ALLOWED_ORIGINS` to the exact HTTPS Vercel origin, with no path or trailing wildcard; redeploy Render. |
| Frontend calls localhost | Set `VITE_API_URL` in Vercel and redeploy the frontend. |
| Saved AI configuration cannot decrypt | Restore the original Render `AI_CREDENTIAL_ENCRYPTION_KEY`, or re-enter provider credentials. |
| File disappears later | This is expected with Render Free local storage; move file bytes to external object storage before relying on uploads. |

Push normal commits to GitHub to trigger the connected Render and Vercel deployments. After an environment variable change, manually redeploy the affected service (and Vercel after `VITE_API_URL` changes).

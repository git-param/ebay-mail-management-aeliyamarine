# ACES Mail Management

ACES is an internal eBay support and operations platform. It connects eBay seller accounts, synchronizes conversations, messages, orders, listings, and offers, and gives teams one React workspace for inbox operations, categorization, assignments, reporting, PMS, daily tasks, leave management, offer management, and sold-posting workflows.

## Documentation

- [API documentation](API.md)
- [System API reference](docs/api/system-api.md)
- [Outbound eBay API reference](docs/api/ebay-api.md)
- [System architecture](ARCHITECTURE.md)
- [Backend workflow notes](backend/Workflow.md)
- [Conversation product context](backend/docs/conversation_product_context.md)
- [eBay offer management](backend/docs/ebay_offer_management.md)
- [Inbox API notes](backend/docs/inbox_api.md)
- [Message type analytics](backend/docs/message_type_analytics.md)

## Technology Stack

| Layer | Technology | Main entry point |
|---|---|---|
| Frontend | React 19, Vite 8 | `frontend/src/App.jsx` |
| Backend | FastAPI, Pydantic, SQLAlchemy | `backend/app/main.py` |
| Database | PostgreSQL, Alembic | `backend/app/db/session.py` |
| Translation | LibreTranslate | Local service on port `5001` |
| External integration | eBay OAuth and REST/XML APIs | `backend/app/modules/integrations/ebay` |

## Prerequisites

Install Python and `pip`, Node.js and `npm`, PostgreSQL, and Git. All commands below use Windows PowerShell and start from:

```powershell
cd "C:\Users\helLO\Desktop\Mail management"
```

## First-Time Setup

### 1. PostgreSQL

Create an empty PostgreSQL database for ACES. Put its SQLAlchemy connection URL in `backend/.env`, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/mail_management
```

### 2. Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set at least:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/mail_management
SECRET_KEY=replace-with-a-long-random-secret
FRONTEND_URL=http://localhost:5173
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
AUTH_COOKIE_SECURE=false
TRANSLATION_API_URL=http://127.0.0.1:5001
```

For eBay features, also configure:

```dotenv
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
EBAY_REDIRECT_URI=
EBAY_RUNAME=
EBAY_ENVIRONMENT=SANDBOX
EBAY_MARKETPLACE_ID=EBAY_US
```

Use `EBAY_ENVIRONMENT=PRODUCTION` only with production credentials and a production RuName/redirect configuration. Never commit `backend/.env` or OAuth tokens.

Apply database migrations:

```powershell
alembic upgrade head
```

If PowerShell blocks virtual-environment activation, allow scripts for the current process and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Frontend

Open a PowerShell window at the project root:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
```

The default frontend API setting is:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Vite also proxies `/api` requests to `http://127.0.0.1:8000` during local development.

## Start the Project

The complete local application requires three terminals. Keep all three running.

### Terminal 1: FastAPI Backend

```powershell
cd "C:\Users\helLO\Desktop\Mail management\backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend URLs:

- API base: `http://127.0.0.1:8000/api/v1`
- Health check: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

### Terminal 2: React Frontend

```powershell
cd "C:\Users\helLO\Desktop\Mail management\frontend"
npm run dev
```

Open `http://localhost:5173`.

### Terminal 3: LibreTranslate

LibreTranslate is installed by `backend/requirements.txt` and should use the backend virtual environment:

```powershell
cd "C:\Users\helLO\Desktop\Mail management\backend"
.\.venv\Scripts\Activate.ps1
libretranslate --host 0.0.0.0 --port 5001
```

The backend calls it through `TRANSLATION_API_URL=http://127.0.0.1:5001`. The first launch can take longer while language resources are initialized.

## Verify the Local Stack

1. Open `http://127.0.0.1:8000/health`; it should return `{"status":"ok"}`.
2. Open `http://localhost:5173`; the React application should load.
3. Open `http://127.0.0.1:5001/languages`; LibreTranslate should return its supported languages.
4. Open `http://127.0.0.1:8000/docs`; the FastAPI endpoints should be visible.

## Common Commands

Run these from `backend` with `.venv` activated:

```powershell
alembic current
alembic upgrade head
python -m py_compile app\main.py
```

Run these from `frontend`:

```powershell
npm run lint
npm run build
```

## Project Layout

```text
Mail management/
|-- backend/
|   |-- alembic/                 Database migrations
|   |-- app/
|   |   |-- api/v1/              Core FastAPI routes
|   |   |-- core/                Settings and security
|   |   |-- db/                  Database session/base
|   |   |-- models/              Shared SQLAlchemy models
|   |   |-- modules/             Domain modules and eBay integration
|   |   |-- repositories/        Persistence queries
|   |   |-- services/            Application orchestration
|   |   `-- main.py              FastAPI application factory
|   |-- .env.example
|   `-- requirements.txt
|-- frontend/
|   |-- src/pages/               Route-level React screens
|   |-- src/services/            Backend API clients
|   |-- .env.example
|   `-- package.json
|-- API.md
|-- ARCHITECTURE.md
`-- README.md
```

## Runtime Notes

- Most `/api/v1` endpoints require an authenticated access-token cookie or bearer token.
- Administrative endpoints enforce role/permission checks in FastAPI dependencies and services.
- The backend lifespan starts notification cleanup and automatic eBay-sync loops.
- eBay sync writes data to PostgreSQL before the frontend reads it; the frontend does not call eBay directly.
- Reply attachments are stored below the configured `REPLY_ATTACHMENT_UPLOAD_DIR` and uploaded to eBay when supported.
- SMTP settings are optional for core startup but required for password-reset email delivery.

## Troubleshooting

**Backend cannot connect to PostgreSQL:** confirm PostgreSQL is running, the database exists, and `DATABASE_URL` uses a supported PostgreSQL URL.

**Browser login works inconsistently over HTTP:** local development normally requires `AUTH_COOKIE_SECURE=false`. Production should use HTTPS and `AUTH_COOKIE_SECURE=true`.

**Translation fails:** verify Terminal 3 is running and `http://127.0.0.1:5001/languages` responds.

**Frontend receives network/CORS errors:** verify the backend is on port `8000`, `VITE_API_BASE_URL` is correct, and the frontend origin appears in `BACKEND_CORS_ORIGINS`.

**eBay connection fails:** verify the environment, client credentials, OAuth scopes, RuName/redirect URI, and callback URL all belong to the same eBay application environment.

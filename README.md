# PriceLens

Automated SaaS pricing sensitivity modeling, AI feature tier auditing, and market competitor benchmarking.

PriceLens evaluates a software company's packaging and pricing structure in under 45 seconds. It delivers quantitative price elasticity projections, audits feature placement across tiers, benchmarks live competitor pricing pages, and produces an executive-ready 3-page PDF report.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-059669?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-0284c7?style=flat-square&logo=react)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5.0-6366f1?style=flat-square&logo=vite)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)](https://www.postgresql.org/)
[![WeasyPrint](https://img.shields.io/badge/WeasyPrint-HTML%20to%20PDF-be185d?style=flat-square)](https://weasyprint.org/)
[![Groq AI](https://img.shields.io/badge/Groq-Llama%203.3%2070B-f97316?style=flat-square)](https://groq.com/)


## System Architecture

PriceLens uses an asynchronous decoupled architecture. The frontend polls an asynchronous ticket pipeline during analysis, ensuring neither client network connections nor server workers block or timeout during web scraping and AI inference.

```mermaid
flowchart TB
    subgraph Client ["Client Layer (React 18 + Vite)"]
        UI[Responsive SPA Interface]
        AuthCtx[Auth Context & JWT Store]
        AxiosClient[Axios Client + Interceptors]
        Poller[Asynchronous Ticket Poller]
    end

    subgraph Gateway ["API & Security Gateway (FastAPI)"]
        RouterAuth["/auth (JWT, Lockout Protection)"]
        RouterComp["/companies (CRUD & Duplication)"]
        RouterSetup["/setup (AI Scraper, CSV, Seeders)"]
        RouterAnalysis["/analysis (Ticket Dispatch & Polling)"]
        RateLimiter["SlowAPI Rate Limiter"]
    end

    subgraph Workers ["Analysis & Intelligence Pipeline"]
        Scraper["5-Layer Web Scraper (Requests + Playwright)"]
        Mod1["Module 1: Pure Python Elasticity & MRR Math"]
        Mod2["Module 2: Groq AI Feature Tier Audit"]
        Mod3["Module 3: Groq AI Competitor Benchmark"]
        Mod4["Module 4: Groq AI Strategic Restructuring"]
    end

    subgraph Deliverables ["Export & Notification Engine"]
        PDFGen["WeasyPrint Executive 3-Page PDF Generator"]
        Mailer["Email Service (SendGrid / SMTP)"]
    end

    subgraph Persistence ["Data Store (PostgreSQL)"]
        DB[(Relational DB: Users, Companies, Tiers, Reports)]
    end

    UI --> AxiosClient
    AxiosClient --> RateLimiter
    RateLimiter --> RouterAuth & RouterComp & RouterSetup & RouterAnalysis
    RouterAuth & RouterComp --> DB

    RouterSetup --> Scraper
    RouterAnalysis --> Poller
    Poller -.->|Poll every 2s| RouterAnalysis

    RouterAnalysis --> Mod1 & Mod2
    Mod1 & Mod2 --> Mod3
    Mod3 --> Mod4
    Mod4 --> DB
    Mod4 --> PDFGen
    PDFGen --> Mailer
    Mailer -.->|Auto-dispatch Report| UserEmail[Registered User Email]
```


## Detailed Execution Flow

```
1. Input & Onboarding
   ├── Web URL Scrape      -> Headless browser fetches public pricing tables
   ├── CSV Import          -> Parses tiers, prices, subscriber counts, and churn rates
   ├── Manual Wizard       -> Interactive builder with tag clouds and industry suggestions
   └── Instant Demo        -> Preloaded CloudHR Pro sample company

2. Background Analysis Pipeline (Ticket-Based)
   ├── POST /analysis/companies/:id/run creates a persistent ticket in PostgreSQL
   ├── Module 1: Deterministic price elasticity modeling (+10%, +20%, +30% scenarios)
   ├── Module 2: Groq AI audits feature tiering (Gatekeeper, Blocker, Right-Placed)
   ├── Module 3: Scrapes and benchmarks competitor pricing pages
   └── Module 4: Synthesizes Conservative, Aggressive, and Strategic packages

3. Delivery & Output
   ├── Real-time UI updates via ticket status polling
   ├── Publication of interactive 4-module web dashboard
   ├── Compilation of executive 3-page WeasyPrint PDF report
   └── Automatic email delivery with PDF attachment (SendGrid / SMTP)
```


## Core Analysis Modules

### 1. Revenue Sensitivity Modeling (Deterministic Python)
- Calculates baseline Monthly Recurring Revenue (MRR) and Annual Recurring Revenue (ARR).
- Applies sector-calibrated price elasticity coefficients based on target customer segment (SMB, Mid-Market, Enterprise).
- Projects revenue impact and net change across +10%, +20%, and +30% price increases, factoring in predicted customer churn.
- Guaranteed mathematical determinism: Identical inputs consistently yield identical financial models.

### 2. Feature Tier Audit (Groq AI)
- Evaluates feature distribution against SaaS packaging benchmarks.
- Classifies each feature into one of four operational categories:
  - Gatekeeper: High-value enterprise features that drive tier upgrades (e.g., SSO, audit logs, custom roles).
  - Blocker: Essential core capabilities mistakenly placed behind premium paywalls.
  - Right-Placed: Appropriately positioned features matching user willingness to pay.
  - Undifferentiated: Common utilities that do not justify pricing premiums.

### 3. Competitor Benchmarking (5-Layer Scraper + AI)
- Multi-tier extraction engine:
  - Layer 1: Fast asynchronous HTTP request (`requests` / `httpx`).
  - Layer 2: Headless browser automation (`Playwright` Chromium) for dynamic JavaScript applications.
  - Layer 3: Heuristic HTML body extraction stripping boilerplate and navigation.
  - Layer 4: Fallback heuristic text parser.
  - Layer 5: Manual pricing text paste override.
- Compares tier price points, packaging models, and feature parity against competitors.

### 4. Strategic Packaging & Recommendations
- Synthesizes findings into three concrete, actionable strategies:
  - Conservative Plan: Low-risk price increase with minimal expected churn.
  - Aggressive Plan: Maximizes MRR yield for products with strong pricing power.
  - Strategic Plan: Structural re-packaging, moving gatekeeper features to enterprise tiers.


## Repository Layout

```
pricing-analyzer/
├── BACKEND_ARCHITECTURE.md        # Deep dive into backend logic, tests, and workers
├── FRONTEND_ARCHITECTURE.md       # Frontend design system, routing, and dictionary
├── docker-compose.yml             # Local PostgreSQL 16 container definition
│
├── backend/
│   ├── main.py                    # FastAPI application, CORS, and router registration
│   ├── models.py                  # SQLAlchemy declarative relational schemas
│   ├── schemas.py                 # Pydantic v2 validation models
│   ├── database.py                # Async engine and sessionmaker
│   ├── rate_limiter.py            # SlowAPI endpoint rate limiting & brute-force protection
│   ├── url_safety.py              # SSRF protection and URL validation
│   ├── scraper.py                 # Multi-layer competitor pricing page scraper
│   ├── pdf_generator.py           # WeasyPrint 3-page executive PDF generator
│   ├── email_service.py           # SendGrid and SMTP email dispatcher with audit logging
│   ├── build.sh                   # Production build script installing WeasyPrint dependencies
│   ├── requirements.txt           # Python dependencies
│   ├── alembic/                   # Database migrations
│   ├── engine/                    # The four pricing analysis modules
│   │   ├── groq_utils.py          # AI client wrapper with retry logic
│   │   ├── module1_revenue.py     # Deterministic elasticity and MRR modeling
│   │   ├── module2_features.py    # AI feature tier classification
│   │   ├── module3_benchmark.py   # AI competitor value comparison
│   │   └── module4_recommendations.py # AI strategic packaging synthesis
│   ├── routers/                   # HTTP endpoints grouped by domain
│   │   ├── auth.py                # Authentication, password resets, and user sessions
│   │   ├── companies.py           # Company CRUD and duplication
│   │   ├── setup.py               # CSV parsing, web scrapers, and sample seeders
│   │   ├── competitors.py         # Competitor management and scraping
│   │   └── analysis.py            # Analysis execution, ticket polling, and PDF retrieval
│   └── tests/                     # Pytest automated test suite (34 unit & integration tests)
│
└── frontend/
    ├── index.html                 # HTML entry point with modern typography
    ├── package.json               # Node.js dependencies
    ├── vite.config.js             # Vite configuration
    └── src/
        ├── App.jsx                # Application root and route definitions
        ├── main.jsx               # React DOM mounting
        ├── index.css              # Font declarations and root resets
        ├── api/                   # Centralized Axios services with JWT interceptors
        │   ├── client.js          # HTTP client instance
        │   ├── auth.js            # Auth requests
        │   ├── companies.js       # Company API calls
        │   ├── setup.js           # Setup & import endpoints
        │   ├── tiers.js           # Tier and feature management
        │   ├── competitors.js     # Competitor operations
        │   └── analysis.js        # Analysis ticket & report endpoints
        ├── components/            # Reusable UI elements
        │   ├── common/            # AccountModal, StatusBadge
        │   └── layout/            # AppLayout, Sidebar, ProtectedRoute
        ├── context/
        │   └── AuthContext.jsx    # User session state management
        ├── pages/                 # Full-page views
        │   ├── Login.jsx          # Swapped layout authentication
        │   ├── Signup.jsx         # Account creation
        │   ├── ForgotPassword.jsx # Password reset request
        │   ├── ResetPassword.jsx  # Token-based password update
        │   ├── Companies.jsx      # Workspace overview & company switcher
        │   ├── CompanySetup.jsx   # 4-way tier onboarding wizard
        │   ├── PricingTiers.jsx   # Tier configuration and feature management
        │   ├── Competitors.jsx    # Competitor scraping and tracking
        │   ├── RunAnalysis.jsx    # Ticket-based progress and trigger
        │   ├── Report.jsx         # 4-module interactive report & PDF download
        │   ├── CompanyReports.jsx # Company-specific report archive
        │   └── AnalysisHistory.jsx # Global audit log of completed reports
        └── styles/                # Vanilla CSS design system
            ├── variables.css      # CSS variables (colors, typography, shadows)
            ├── global.css         # Universal element styles
            ├── layout.css         # Grid layouts, sidebar styling, split auth screens
            └── components.css     # Buttons, cards, badges, inputs, and tables
```


## Local Development Setup

### Requirements
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (or Docker)
- Groq API Key ([console.groq.com](https://console.groq.com))

### 1. Database Setup (Docker)
```bash
docker compose up -d
```
Starts a PostgreSQL 16 container named `pricelens_db` running on `localhost:5432`.

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries for JS scraping
playwright install chromium

# Configure environment
cp .env.example .env
```

Ensure your `backend/.env` contains the required keys:
```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/pricelens
JWT_SECRET=your-minimum-32-character-secret-key-goes-here-abc123
GROQ_API_KEY=gsk_your_groq_api_key_here
FRONTEND_URL=http://localhost:5173
```

Run database migrations and start the server:
```bash
alembic upgrade head
uvicorn main:app --reload --port 8000
```
Backend API will be accessible at `http://localhost:8000`.  
Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### 3. Frontend Setup
```bash
cd frontend

# Install Node dependencies
npm install

# Configure environment
cp .env.example .env
```

Start Vite dev server:
```bash
npm run dev
```
Frontend will be accessible at `http://localhost:5173` (or `http://localhost:5174`).


## Automated Test Suite

The backend contains 34 automated unit and integration tests covering the analysis engine, authentication, security rate limits, and URL safety.

```bash
cd backend
pytest tests/
```

Test coverage includes:
- `test_analysis_reliability.py`: Verifies mathematical determinism and error tolerance across analysis modules.
- `test_login_tokens.py`: Validates JWT token issuance, verification, and revocation.
- `test_ownership.py`: Ensures strict multi-tenant isolation (users cannot access another tenant's companies).
- `test_password_reset.py`: Tests secure token generation, expiration, and password update logic.
- `test_rate_limits.py`: Verifies brute-force protection and lockout thresholds on auth endpoints.
- `test_setup_features.py`: Tests CSV import, AI URL extraction, and sample company generation.
- `test_url_safety.py`: Validates SSRF prevention, blocking localhost and internal IP scraping.


## Email Delivery Configuration

PriceLens automatically emails completed analysis reports with the 3-page PDF attached. Configure one of the options below in `backend/.env`:

### Option A: SendGrid API
```env
SENDGRID_API_KEY=SG.your_api_key_here
FROM_EMAIL=notifications@yourdomain.com
```

### Option B: Standard SMTP (e.g., Gmail)
```env
FROM_EMAIL=your-account@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-account@gmail.com
SMTP_PASS=your-16-character-app-password
```

### Option C: Offline / Development Simulation
If no email credentials are provided, PriceLens logs delivery details to `backend/generated_pdfs/outgoing_emails.json` without interrupting execution.


## Production Deployment

### Backend (Render)
1. Create a new Web Service pointing to your repository.
2. Set Root Directory to `backend`.
3. Set Build Command to `./build.sh` (installs Pango, Cairo, and system packages for WeasyPrint).
4. Set Start Command to `uvicorn main:app --host 0.0.0.0 --port $PORT`.
5. Supply the required environment variables:
   - `DATABASE_URL`: Connection string from your managed PostgreSQL instance.
   - `JWT_SECRET`: Random 64-character secret.
   - `GROQ_API_KEY`: Production Groq key.
   - `FRONTEND_URL`: URL of your deployed Vercel frontend.

### Frontend (Vercel)
1. Import repository into Vercel.
2. Set Root Directory to `frontend`.
3. Add Environment Variable:
   - `VITE_API_URL`: URL of your deployed backend (e.g., `https://pricelens-api.onrender.com`).
4. Build command: `npm run build`.
5. Output directory: `dist`.


import os

from pathlib import Path

from contextlib import asynccontextmanager

from dotenv import load_dotenv

from sqlalchemy import text

env_path = Path(__file__).resolve().parent / ".env"

load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime
from database import engine, Base, AsyncSessionLocal
from models import AnalysisSession
from sqlalchemy.future import select
from routers import auth, companies, analysis, competitors, setup
from groq import Groq

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sweep any sessions left running from a previous crash/restart
    try:
        async with AsyncSessionLocal() as db:
            running_sessions_result = await db.execute(
                select(AnalysisSession).where(AnalysisSession.status == "running")
            )
            interrupted = running_sessions_result.scalars().all()
            for session in interrupted:
                session.status = "failed"
                session.progress = 100
                session.error_message = "The server restarted during this analysis. Please run it again."
                session.completed_at = datetime.utcnow()
            if interrupted:
                await db.commit()
                print(f"INFO: Marked {len(interrupted)} interrupted running session(s) as failed.")
    except Exception as e:
        print(f"WARNING: Could not sweep running sessions on startup: {e}")

    pdf_dir = os.path.join(os.path.dirname(__file__), "generated_pdfs")
    os.makedirs(pdf_dir, exist_ok=True)  # creates the folder silently if missing



    api_key = os.getenv("GROQ_API_KEY", "")  # "" = default if the key is missing

    print(f"DEBUG: GROQ_API_KEY loaded = {'YES' if api_key else 'NO — check .env file'}")

    if api_key:
        app.state.groq_client = Groq(api_key=api_key)
        print("SUCCESS: Groq client initialized.")
    else:
        app.state.groq_client = None
        print("WARNING: GROQ_API_KEY not set.")  # AI analysis will return empty stubs

    if os.getenv("SENDGRID_API_KEY", "") and os.getenv("FROM_EMAIL", ""):
        print("SUCCESS: Email notifications enabled (SendGrid).")
    else:
        print("INFO: SendGrid credentials not set; email notifications disabled.")

    yield


from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from rate_limiter import limiter, custom_rate_limit_exceeded_handler

app = FastAPI(
    title="SaaS Pricing Analyzer API",                               # shown in /docs
    description="Automated SaaS Pricing Sensitivity Analyzer — backend API",  # shown in /docs
    version="1.0.0",                                                  # API version string
    lifespan=lifespan,                                                # startup/shutdown logic
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)


frontend_url = os.getenv("FRONTEND_URL", "https://pricelens.vercel.app")
default_cors_origins = [
    "http://localhost:5173",       # React dev server (Vite default port)
    "http://localhost:5174",       # Vite alternate port
    "http://localhost:5175",       # Vite alternate port
    "http://localhost:3000",       # React dev server (Create React App default port)
    frontend_url,                  # deployed Vercel production frontend URL
    "https://pricelens.vercel.app",             # Production Vercel URL
    "https://pricing-analyzer-32hw.vercel.app", # Alternative Vercel URL
    "https://pricelens-app.vercel.app",
]

cors_env = os.getenv("CORS_ORIGINS")
if cors_env:
    cors_origins = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
else:
    cors_origins = list(dict.fromkeys(default_cors_origins))

app.add_middleware(
    CORSMiddleware,                    # the middleware class to use
    allow_origins=cors_origins,        # list of domains allowed to call this API
    allow_credentials=True,           # allow cookies and Authorization headers to be sent
    allow_methods=["*"],              # allow all HTTP methods (GET, POST, DELETE, etc.)
    allow_headers=["*"],              # allow all headers (including Authorization for JWT)
)


app.include_router(auth.router, prefix="/auth", tags=["auth"])

app.include_router(companies.router, prefix="/companies", tags=["companies"])

app.include_router(competitors.router, prefix="/companies", tags=["competitors"])

app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])

app.include_router(setup.router, prefix="/setup", tags=["setup"])



@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "version": "1.0.0"}

@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root():
    return {
        "message": "PriceLens API is running!"
    }

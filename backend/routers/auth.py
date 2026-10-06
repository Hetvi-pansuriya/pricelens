"""
auth.py (routers/auth.py)
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Handles all user authentication endpoints.

Endpoints:
  POST /auth/signup           → create new account, return JWT
  POST /auth/login            → verify credentials, return JWT
  GET  /auth/me               → get current user profile
  POST /auth/forgot-password  → send password reset email
  POST /auth/reset-password   → validate token, set new password
  DELETE /auth/account        → delete user account and all their data

Also exports: get_current_user() — a FastAPI dependency used by ALL other
routers to authenticate requests via the JWT Bearer token.

CONNECTED TO:
  - main.py       → registers this router with prefix="/auth"
  - database.py   → uses get_db() dependency for DB sessions
  - models.py     → queries User and PasswordResetToken models
  - schemas.py    → uses UserCreate, LoginRequest, TokenResponse, etc.
  - All other routers import get_current_user from here for auth checks.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import hashlib
import secrets

import uuid

from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from jose import JWTError, jwt

from passlib.context import CryptContext

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.future import select

from database import get_db

from models import PasswordResetToken, User

from pydantic import BaseModel, EmailStr

from schemas import (
    UserCreate,          # POST /signup request body
    LoginRequest,        # POST /login request body
    ResetPasswordBody,   # POST /reset-password request body
    UserResponse,        # used in GET /auth/me and get_current_user
    TokenResponse,       # returned by /signup and /login
)


class ForgotPasswordRequest(BaseModel):
    """Only email is needed to initiate a password reset."""
    email: EmailStr

from rate_limiter import (
    limiter,
    check_login_lockout,
    record_failed_login,
    clear_failed_logins,
)

router = APIRouter()


SECRET_KEY = os.getenv("JWT_SECRET", "")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "CRITICAL: JWT_SECRET environment variable is missing or shorter than 32 characters. "
        "The application cannot start securely. Please set a JWT_SECRET with at least 32 characters."
    )

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer(auto_error=False)



def hash_password(password: str) -> str:
    return pwd_context.hash(password)  # bcrypt hash with random salt


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)  # bcrypt comparison (timing-safe)


def create_access_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),  # subject: the user's UUID as a string
        "exp": datetime.utcnow() + timedelta(hours=EXPIRE_HOURS),  # expiry: now + 24h
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)  # re-declared for clarity (same as above)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),  # Bearer header only
    db: AsyncSession = Depends(get_db),  # DB session for user lookup
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},  # standard response header for 401
    )

    if not credentials or not credentials.credentials:
        raise credentials_exception

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


        user_id: Optional[str] = payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user



@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def signup(request: Request, body: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()  # returns User or None

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        id=uuid.uuid4(),                           # generate a new random UUID
        email=body.email,                          # the validated email from the request body
        password_hash=hash_password(body.password),  # bcrypt-hash the password before storing
        created_at=datetime.utcnow(),              # record the registration timestamp
    )
    db.add(user)       # stage the new user row for insertion
    await db.commit()  # execute the INSERT to PostgreSQL
    await db.refresh(user)  # reload the user from DB (populates any DB-generated fields)

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)  # returns {"access_token": "eyJ...", "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    check_login_lockout(body.email)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()  # None if email not found

    if not user or not verify_password(body.password, user.password_hash):
        record_failed_login(body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",  # intentionally vague
        )

    clear_failed_logins(body.email)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Always return success to prevent account enumeration."""
    message = {"message": "If this email exists, a reset link has been sent."}

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        return message  # don't reveal that the email isn't registered

    old_tokens = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    for old_token in old_tokens.scalars().all():
        await db.delete(old_token)  # remove each old token

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    db.add(
        PasswordResetToken(
            id=uuid.uuid4(),                              # new UUID for this token row
            user_id=user.id,                             # links to the user
            token=token_hash,                            # store SHA-256 hash only
            expires_at=datetime.utcnow() + timedelta(hours=1),  # 1 hour from now
        )
    )
    await db.commit()  # save the hashed token to the DB

    reset_link = (
        f"{os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')}"
        f"/reset-password?token={raw_token}"
    )

    try:
        from email_service import send_password_reset_email  # optional module
        await send_password_reset_email(user.email, reset_link)
    except Exception as error:
        print(f"[Email] Reset email failed (non-fatal): {error}")

    return message  # always return success regardless of email delivery


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: ResetPasswordBody,       # contains "token" and "new_password"
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token_hash)
    )
    reset = result.scalar_one_or_none()  # None if token doesn't exist

    if (
        not reset
        or reset.used == "yes"
        or reset.expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset link.",
        )

    user_result = await db.execute(select(User).where(User.id == reset.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")  # shouldn't happen

    user.password_hash = hash_password(body.new_password)  # bcrypt the new password

    reset.used = "yes"

    await db.commit()  # save both changes to the DB in one transaction
    return {"message": "Password updated successfully."}


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),  # must be authenticated
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)  # mark for deletion (CASCADE will handle all related data)
    await db.commit()      # execute the DELETE — all user data is permanently removed

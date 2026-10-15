"""Auth routes — register, login, logout, refresh, me"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Response, Cookie, Request
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.database import get_db
from core.security import (
    sign_access_token, sign_refresh_token,
    verify_refresh_token, hash_refresh_token, get_token_payload
)
from core.errors import not_found, unauthorized, conflict
from models.models import User, UserProfile, Session
from models.schemas import RegisterBody, LoginBody

router = APIRouter(prefix="/api/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_OPTS = {"httponly": True, "samesite": "lax"}


def _set_tokens(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, max_age=15 * 60, **COOKIE_OPTS)
    response.set_cookie("refresh_token", refresh, max_age=7 * 24 * 3600, **COOKIE_OPTS)


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise conflict("An account with this email already exists")

    password_hash = pwd_context.hash(body.password)
    user_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())

    user = User(id=user_id, email=body.email, password_hash=password_hash)
    profile = UserProfile(id=profile_id, user_id=user_id, display_name=body.display_name)
    db.add(user)
    db.add(profile)

    access = sign_access_token(user_id, "STUDENT")
    refresh = sign_refresh_token(user_id, "STUDENT")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        token=hash_refresh_token(refresh),
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    await db.commit()

    _set_tokens(response, access, refresh)
    return {"success": True, "data": {
        "user": {"id": user_id, "email": body.email, "role": "STUDENT",
                 "profile": {"displayName": body.display_name}},
        "accessToken": access,
    }}


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(User.email == body.email)
    )
    if not user:
        raise unauthorized("Invalid email or password")
    if not user.is_active:
        raise unauthorized("Your account has been deactivated")
    if not pwd_context.verify(body.password, user.password_hash):
        raise unauthorized("Invalid email or password")

    # Load profile
    profile_row = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))

    access = sign_access_token(user.id, user.role.value)
    refresh = sign_refresh_token(user.id, user.role.value)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token=hash_refresh_token(refresh),
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    await db.commit()

    _set_tokens(response, access, refresh)
    return {"success": True, "data": {
        "user": {
            "id": user.id, "email": user.email, "role": user.role.value,
            "profile": {"displayName": profile_row.display_name, "avatarUrl": profile_row.avatar_url} if profile_row else None,
        },
        "accessToken": access,
    }}


@router.post("/logout")
async def logout(response: Response, refresh_token: Optional[str] = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        await db.execute(delete(Session).where(Session.token == token_hash))
        await db.commit()
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"success": True, "message": "Logged out successfully"}


@router.post("/refresh")
async def refresh(request: Request, response: Response, refresh_token: Optional[str] = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if not refresh_token:
        raise unauthorized("Refresh token missing")
    payload = verify_refresh_token(refresh_token)
    token_hash = hash_refresh_token(refresh_token)
    session = await db.scalar(select(Session).where(Session.token == token_hash))
    if not session or session.user_id != payload["userId"] or session.expires_at < datetime.now(timezone.utc):
        raise unauthorized("Session expired, please login again")

    user = await db.scalar(select(User).where(User.id == payload["userId"]))
    if not user or not user.is_active:
        raise unauthorized("Account not found")

    access = sign_access_token(user.id, user.role.value)
    new_refresh = sign_refresh_token(user.id, user.role.value)
    new_expires = datetime.now(timezone.utc) + timedelta(days=7)

    await db.delete(session)
    new_session = Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token=hash_refresh_token(new_refresh),
        expires_at=new_expires,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(new_session)
    await db.commit()

    _set_tokens(response, access, new_refresh)
    return {"success": True, "data": {"accessToken": access}}


@router.get("/me")
async def get_me(payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == payload["userId"]))
    if not user:
        raise not_found("User")
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    return {"success": True, "data": {"user": {
        "id": user.id, "email": user.email, "role": user.role.value,
        "emailVerified": user.email_verified, "createdAt": user.created_at.isoformat(),
        "profile": {
            "displayName": profile.display_name, "bio": profile.bio,
            "avatarUrl": profile.avatar_url, "college": profile.college,
            "skills": profile.skills, "interests": profile.interests,
            "isPublic": profile.is_public,
        } if profile else None,
    }}}

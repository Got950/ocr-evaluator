from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Institution, User, get_db
from app.services.auth_service import create_access_token, hash_password, verify_password
from app.dependencies import get_current_user


router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    role: str = Field(default="student")
    institution_name: Optional[str] = None


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    institution_id: Optional[uuid.UUID] = None


@router.post("/auth/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    if payload.role not in ("professor", "student", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")

    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    institution_id = None
    if payload.institution_name:
        inst = (await db.execute(select(Institution).where(Institution.name == payload.institution_name))).scalar_one_or_none()
        if inst is None:
            inst = Institution(name=payload.institution_name)
            db.add(inst)
            await db.flush()
        institution_id = inst.id

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        institution_id=institution_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return RegisterResponse(user_id=user.id, email=user.email, role=user.role)


@router.post("/auth/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = (await db.execute(select(User).where(User.email == form.username))).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        institution_id=current_user.institution_id,
    )

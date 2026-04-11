from fastapi import APIRouter, Depends, HTTPException
import uuid
import hashlib
from typing import Any
from sqlalchemy import select

from core.database import AsyncSessionLocal, User
from pydantic import BaseModel

router = APIRouter()

class AuthSignup(BaseModel):
    name: str
    email: str
    password: str

class AuthLogin(BaseModel):
    email: str
    password: str

def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/auth/signup")
async def signup(payload: AuthSignup):
    async with AsyncSessionLocal() as session:
        # Check if user exists
        res = await session.execute(select(User).where(User.email == payload.email))
        if res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
            
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            name=payload.name,
            email=payload.email,
            password_hash=get_password_hash(payload.password)
        )
        session.add(user)
        try:
            await session.commit()
        except:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Database error")
            
        return {"token": f"user_{user_id}", "user": {"id": user.id, "name": user.name, "email": user.email}}

@router.post("/auth/login")
async def login(payload: AuthLogin):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.email == payload.email))
        user = res.scalar_one_or_none()
        
        if not user or user.password_hash != get_password_hash(payload.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
        return {"token": f"user_{user.id}", "user": {"id": user.id, "name": user.name, "email": user.email}}

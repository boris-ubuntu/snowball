"""
JWT Authentication module
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# User credentials — password from environment variable
# For production (Render), set BORIS_PASSWORD in Dashboard Environment Variables
# For local development, falls back to the default password
_BORIS_PASSWORD = os.getenv("BORIS_PASSWORD", "Maelstormer5")
USERS = {
    "boris": {
        "username": "boris",
        "password": _BORIS_PASSWORD,
        "full_name": "Boris",
    }
}

from .config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = USERS.get(username)
    if not user:
        return None
    if user["password"] != password:
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Dependency to get current user from token. Returns None if no token."""
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        user = USERS.get(username)
        return user
    except JWTError:
        return None


async def require_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Dependency that requires authentication."""
    user = await get_current_user(credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
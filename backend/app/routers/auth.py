"""
Authentication router - login endpoint
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.auth import authenticate_user, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    """Authenticate user and return JWT token"""
    user = authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
        )
    
    access_token = create_access_token(data={"sub": user["username"]})
    return LoginResponse(
        access_token=access_token,
        username=user["username"],
        full_name=user["full_name"],
    )
"""
用户认证 API：注册、登录。
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient

from app.core.auth import create_access_token, hash_password, verify_password
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# 请求 / 响应 Schema
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


# ---------------------------------------------------------------------------
# 工具：获取 users 集合
# ---------------------------------------------------------------------------

def _get_users_collection():
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.DB_NAME]
    return client, db["users"]


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> TokenResponse:
    """
    创建新用户账号。

    - email 必须唯一（重复注册返回 409）
    - 密码使用 bcrypt 单向哈希存储，原文不入库
    - 注册成功直接返回 JWT，无需二次登录
    """
    client, users = _get_users_collection()
    try:
        if users.find_one({"email": payload.email}):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered.",
            )

        user_id = str(uuid.uuid4())
        hashed = hash_password(payload.password)
        users.insert_one(
            {
                "user_id": user_id,
                "email": payload.email,
                "hashed_password": hashed,
            }
        )

        token = create_access_token(user_id, payload.email)
        return TokenResponse(
            access_token=token,
            user_id=user_id,
            email=payload.email,
        )
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """
    验证邮箱和密码，签发 JWT。

    - 邮箱不存在或密码错误均返回 401（不区分，防止枚举攻击）
    """
    client, users = _get_users_collection()
    try:
        user = users.find_one({"email": payload.email})
        if not user or not verify_password(payload.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(user["user_id"], payload.email)
        return TokenResponse(
            access_token=token,
            user_id=user["user_id"],
            email=payload.email,
        )
    finally:
        client.close()

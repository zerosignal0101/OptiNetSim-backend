from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid6 import uuid7


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username for the account")


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100, description="Password for the account")


class UserInDB(UserBase):
    id: str = Field(default_factory=lambda: str(uuid7()), description="Unique user identifier")
    hashed_password: str = Field(..., description="Hashed password")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Account creation timestamp")
    is_active: bool = Field(default=True, description="Whether the user account is active")


class UserResponse(BaseModel):
    id: str
    username: str
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str = Field(..., description="Username for login")
    password: str = Field(..., description="Password for login")


class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenData(BaseModel):
    username: Optional[str] = None
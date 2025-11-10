from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings
from app.models.user import UserInDB, TokenData

# JWT token scheme
security = HTTPBearer()

# Settings instance
settings = get_settings()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        # bcrypt automatically handles the 72-character limit
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    try:
        # bcrypt automatically handles the 72-character limit and adds salt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to hash password: {e}")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """Verify JWT token and extract user data."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data = TokenData(username=username)
        return token_data
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    token_data = verify_token(token)
    return token_data


async def get_current_active_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Get current active user (placeholder for future user status checks)."""
    # In a full implementation, you would fetch the user from database here
    # and check if they are active
    return current_user
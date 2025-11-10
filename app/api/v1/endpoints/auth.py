from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from app.models.user import UserCreate, UserLogin, Token, UserResponse
from app.crud.crud_user import crud_user
from app.core.auth import create_access_token, get_current_user, verify_token
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """
    Register a new user.

    - **username**: Unique username for the account (3-50 characters)
    - **password**: Password for the account (6-100 characters)
    """
    try:
        created_user = await crud_user.create_user(user)
        return created_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin):
    """
    Authenticate user and return access token.

    - **username**: Registered username
    - **password**: User password
    """
    # Authenticate user
    user = await crud_user.authenticate_user(user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.delete("/delete", status_code=status.HTTP_200_OK)
async def delete_user(current_user: str = Depends(get_current_user)):
    """
    Delete currently authenticated user's account.

    Requires JWT authentication token.
    """
    try:
        success = await crud_user.delete_user(current_user.username)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return {"msg": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """
    Get current authenticated user information.

    Requires JWT authentication token.
    """
    try:
        user = await crud_user.get_user_by_username(current_user.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return UserResponse(
            id=user.id,
            username=user.username,
            created_at=user.created_at,
            is_active=user.is_active
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )
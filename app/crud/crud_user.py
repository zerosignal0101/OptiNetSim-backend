from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.database import get_database
from app.models.user import UserInDB, UserCreate, UserResponse
from app.core.auth import get_password_hash, verify_password
from bson import ObjectId


class CRUDUser:
    def __init__(self):
        self.collection_name = "users"

    async def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        """Get user by username."""
        db = get_database()
        user_doc = await db[self.collection_name].find_one({"username": username})
        if user_doc:
            return UserInDB(**user_doc)
        return None

    async def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        """Get user by ID."""
        db = get_database()
        try:
            user_doc = await db[self.collection_name].find_one({"_id": ObjectId(user_id)})
            if user_doc:
                user_doc["id"] = str(user_doc.pop("_id"))
                return UserInDB(**user_doc)
        except Exception:
            pass
        return None

    async def create_user(self, user_create: UserCreate) -> UserResponse:
        """Create a new user."""
        db = get_database()

        # Check if user already exists
        existing_user = await self.get_user_by_username(user_create.username)
        if existing_user:
            raise ValueError("Username already registered")

        # Create user document
        user_in_db = UserInDB(
            username=user_create.username,
            hashed_password=get_password_hash(user_create.password)
        )

        # Insert into database
        result = await db[self.collection_name].insert_one(user_in_db.model_dump(by_alias=True, exclude={"id"}))

        # Return user response
        return UserResponse(
            id=str(result.inserted_id),
            username=user_in_db.username,
            created_at=user_in_db.created_at,
            is_active=user_in_db.is_active
        )

    async def authenticate_user(self, username: str, password: str) -> Optional[UserInDB]:
        """Authenticate user with username and password."""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def delete_user(self, username: str) -> bool:
        """Delete user by username."""
        db = get_database()
        result = await db[self.collection_name].delete_one({"username": username})
        return result.deleted_count > 0


# Create a singleton instance
crud_user = CRUDUser()
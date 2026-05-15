from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password):
        return None
    return user


async def create_default_operator(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.username == "operator"))
    if result.scalar_one_or_none() is None:
        db.add(User(username="operator", password=hash_password("operator123")))
        await db.commit()

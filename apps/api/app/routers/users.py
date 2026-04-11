from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, response: Response, db: Session = Depends(get_db)) -> User:
    normalized_email = payload.email.strip().lower()
    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    user = User(email=normalized_email)
    db.add(user)

    db.commit()

    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())

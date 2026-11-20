"""
POST /auth/login (TokenOut) and GET /me (CurrentUser).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.engine import Connection

from app.core.deps import get_current_user, get_db
from app.schemas import CurrentUser, LoginRequest, TokenOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenOut, status_code=status.HTTP_200_OK)
def login(
    request: LoginRequest,
    db: Annotated[Connection, Depends(get_db)],
) -> TokenOut:
    return auth_service.login(db, request)


@me_router.get("/me", response_model=CurrentUser)
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    return user

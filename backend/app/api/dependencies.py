from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.constants.auth_constants import AuthMessages
from app.core.security import decode_token
from app.db.session import get_db
from app.repositories.auth_repository import AuthRepository


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.MISSING_AUTH_TOKEN)

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_AUTH_TOKEN) from exc

    if payload.get('type') != 'access' or not payload.get('sub'):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_AUTH_TOKEN)

    user = AuthRepository(db).get_user_by_id(UUID(payload['sub']))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthMessages.INVALID_AUTH_TOKEN)
    return user

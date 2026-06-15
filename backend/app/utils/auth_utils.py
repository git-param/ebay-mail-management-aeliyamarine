from fastapi import HTTPException, status

from app.constants.auth_constants import AuthMessages, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.core.security import verify_password


def validate_password_rules(password: str) -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return AuthMessages.PASSWORD_TOO_SHORT
    if len(password) > PASSWORD_MAX_LENGTH:
        return AuthMessages.PASSWORD_TOO_LONG
    if not any(char.isalpha() for char in password):
        return AuthMessages.PASSWORD_NEEDS_LETTER
    if not any(char.isdigit() for char in password):
        return AuthMessages.PASSWORD_NEEDS_NUMBER
    return None


def ensure_new_password_is_valid(*, new_password: str, current_password_hash: str) -> None:
    error = validate_password_rules(new_password)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    if verify_password(new_password, current_password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=AuthMessages.PASSWORD_REUSED)

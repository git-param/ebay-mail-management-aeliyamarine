from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserCreateRequest, UserResponse, UserUpdateRequest
from app.services.auth_service import AuthService
from app.utils.auth_utils import validate_password_rules


router = APIRouter()

ROLE_ALIASES = {
    'ADMIN': 'Admin',
    'OPS_MANAGER': 'Operations Manager',
    'OPERATIONS_MANAGER': 'Operations Manager',
    'AGENT': 'Support Agent',
    'SUPPORT_AGENT': 'Support Agent',
}


def require_admin(current_user=Depends(get_current_user)):
    if current_user.role.name != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can manage users')
    return current_user


def normalize_role_name(role: str) -> str:
    role_key = role.strip().upper().replace('-', '_').replace(' ', '_')
    return ROLE_ALIASES.get(role_key, role.strip())


def display_role_name(role_name: str) -> str:
    if role_name == 'Support Agent':
        return 'Agent'
    return role_name


def get_role(db: Session, role: str) -> Role:
    role_name = normalize_role_name(role)
    existing_role = db.scalar(select(Role).where(Role.name == role_name))
    if not existing_role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid role')
    return existing_role


def get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.scalar(select(User).options(joinedload(User.role)).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    return user


def serialize_user(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=display_role_name(user.role.name),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get('', response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> list[UserResponse]:
    statement = select(User).options(joinedload(User.role)).order_by(User.created_at.desc())
    return [serialize_user(user) for user in db.scalars(statement)]


@router.post('', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    normalized_email = payload.email.lower().strip()
    existing_user = db.scalar(select(User).where(User.email == normalized_email))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='A user with this email already exists')

    password_error = validate_password_rules(payload.password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)

    role = get_role(db, payload.role)
    user = User(
        email=normalized_email,
        full_name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role_id=role.id,
        is_active=payload.is_active,
        must_reset_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user.role = role
    return serialize_user(user)


@router.get('/{user_id}', response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    return serialize_user(get_user_or_404(db, user_id))


@router.put('/{user_id}', response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    user = get_user_or_404(db, user_id)
    normalized_email = payload.email.lower().strip()
    duplicate_user = db.scalar(select(User).where(User.email == normalized_email).where(User.id != user_id))
    if duplicate_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='A user with this email already exists')

    role = get_role(db, payload.role)
    user.full_name = payload.name.strip()
    user.email = normalized_email
    user.role_id = role.id
    user.role = role
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.patch('/{user_id}/activate', response_model=UserResponse)
def activate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    user = get_user_or_404(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.patch('/{user_id}/deactivate', response_model=UserResponse)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    user = get_user_or_404(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.post('/{user_id}/reset-password')
def reset_user_password(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> dict[str, str]:
    user = get_user_or_404(db, user_id)
    AuthService(db).request_password_reset(email=user.email)
    return {'message': 'Password reset notification sent'}

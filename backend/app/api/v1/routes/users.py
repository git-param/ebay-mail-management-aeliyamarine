from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.category import Category, CategoryUserAssignment
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
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

USER_ENTITY_TYPE = 'USER'


class UserAuditActions:
    CREATED = 'USER_CREATED'
    UPDATED = 'USER_UPDATED'
    ACTIVATED = 'USER_ACTIVATED'
    DEACTIVATED = 'USER_DEACTIVATED'
    DELETED = 'USER_DELETED'
    PASSWORD_RESET_REQUESTED = 'USER_PASSWORD_RESET_REQUESTED'


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


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def get_role(db: Session, role: str) -> Role:
    role_name = normalize_role_name(role)
    existing_role = db.scalar(select(Role).where(Role.name == role_name))
    if not existing_role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid role')
    return existing_role


def get_user_or_404(db: Session, user_id: UUID, *, include_deleted: bool = False) -> User:
    statement = select(User).options(joinedload(User.role)).where(User.id == user_id)
    if not include_deleted:
        statement = statement.where(User.deleted_at.is_(None))
    user = db.scalar(statement)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    return user


def assigned_categories_for_user(db: Session, user_id: UUID) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .join(CategoryUserAssignment, CategoryUserAssignment.category_id == Category.id)
            .where(CategoryUserAssignment.user_id == user_id)
            .order_by(Category.name.asc())
        )
    )


def serialize_user(user: User) -> UserResponse:
    assigned_categories = assigned_categories_for_user(user._sa_instance_state.session, user.id)
    return UserResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=display_role_name(user.role.name),
        is_active=user.is_active,
        employee_id=user.employee_id,
        department=user.department,
        designation=user.designation,
        date_of_joining=user.date_of_joining,
        created_at=user.created_at,
        updated_at=user.updated_at,
        assigned_categories=[category.name for category in assigned_categories],
        assigned_category_ids=[category.id for category in assigned_categories],
    )


def add_user_audit_log(db: Session, *, action: str, actor_id: UUID, target_user_id: UUID) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type=USER_ENTITY_TYPE,
            entity_id=target_user_id,
        )
    )


@router.get('', response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[UserResponse]:
    statement = (
        select(User)
        .options(joinedload(User.role))
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
    )
    return [serialize_user(user) for user in db.scalars(statement)]


@router.post('', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> UserResponse:
    normalized_email = payload.email.lower().strip()
    existing_user = db.scalar(select(User).where(User.email == normalized_email).where(User.deleted_at.is_(None)))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='A user with this email already exists')

    password_error = validate_password_rules(payload.password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)

    role = get_role(db, payload.role)
    user = User(
        email=normalized_email,
        full_name=payload.name.strip(),
        employee_id=clean_optional_text(payload.employee_id),
        department=clean_optional_text(payload.department),
        designation=clean_optional_text(payload.designation),
        date_of_joining=payload.date_of_joining,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        is_active=payload.is_active,
        must_reset_password=False,
    )
    db.add(user)
    db.flush()
    add_user_audit_log(
        db,
        action=UserAuditActions.CREATED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
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
    duplicate_user = db.scalar(
        select(User)
        .where(User.email == normalized_email)
        .where(User.id != user_id)
        .where(User.deleted_at.is_(None))
    )
    if duplicate_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='A user with this email already exists')

    role = get_role(db, payload.role)
    user.full_name = payload.name.strip()
    user.email = normalized_email
    user.employee_id = clean_optional_text(payload.employee_id)
    user.department = clean_optional_text(payload.department)
    user.designation = clean_optional_text(payload.designation)
    user.date_of_joining = payload.date_of_joining
    user.role_id = role.id
    user.role = role
    user.is_active = payload.is_active
    add_user_audit_log(
        db,
        action=UserAuditActions.UPDATED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
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
    add_user_audit_log(
        db,
        action=UserAuditActions.ACTIVATED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
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
    add_user_audit_log(
        db,
        action=UserAuditActions.DEACTIVATED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.delete('/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> None:
    if str(current_user.id) == str(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='You cannot delete your own user account')

    user = get_user_or_404(db, user_id)
    deleted_at = datetime.now(UTC)

    user.is_active = False
    user.deleted_at = deleted_at
    user.deleted_by_user_id = current_user.id
    user.email = f'deleted-{user.id}@deleted.local'

    db.execute(delete(CategoryUserAssignment).where(CategoryUserAssignment.user_id == user.id))
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    for token in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id).where(RefreshToken.revoked_at.is_(None))):
        token.revoked_at = deleted_at

    add_user_audit_log(
        db,
        action=UserAuditActions.DELETED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
    db.commit()


@router.post('/{user_id}/reset-password')
def reset_user_password(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> dict[str, str]:
    user = get_user_or_404(db, user_id)
    AuthService(db).request_password_reset(email=user.email)
    add_user_audit_log(
        db,
        action=UserAuditActions.PASSWORD_RESET_REQUESTED,
        actor_id=current_user.id,
        target_user_id=user.id,
    )
    db.commit()
    return {'message': 'Password reset notification sent'}

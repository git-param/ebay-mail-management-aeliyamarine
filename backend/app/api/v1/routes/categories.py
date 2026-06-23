from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_current_user, require_operations_manager_or_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.category import Category, CategoryKeyword, CategoryUserAssignment
from app.models.user import User
from app.schemas.category import (
    CategoryAssigneeResponse,
    CategoryCreateRequest,
    CategoryKeywordCreateRequest,
    CategoryKeywordResponse,
    CategoryResponse,
    CategoryUpdateRequest,
    UserCategoryAssignmentRequest,
)
from app.services.audit_service import AuditService
from app.services.category_assignment_service import CategoryAssignmentService
from app.services.category_service import (
    ensure_category_name_available,
    ensure_keyword_available,
    get_category_or_404,
    validate_unique_keywords,
)


router = APIRouter()

CATEGORY_ENTITY_TYPE = 'CATEGORY'


class CategoryAuditActions:
    CREATED = 'CATEGORY_CREATED'
    UPDATED = 'CATEGORY_UPDATED'
    ACTIVATED = 'CATEGORY_ACTIVATED'
    DEACTIVATED = 'CATEGORY_DEACTIVATED'
    DELETED = 'CATEGORY_DELETED'
    KEYWORD_CREATED = 'CATEGORY_KEYWORD_CREATED'
    KEYWORD_DELETED = 'CATEGORY_KEYWORD_DELETED'
    ASSIGNMENTS_UPDATED = 'CATEGORY_ASSIGNMENTS_UPDATED'


def role_name(current_user) -> str:
    return current_user.role.name


def require_category_access(current_user=Depends(get_current_user)):
    if role_name(current_user) not in {'Admin', 'Operations Manager', 'Support Agent'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You do not have access to categories')
    return current_user


def require_category_assignment_access(current_user=Depends(require_operations_manager_or_admin)):
    return current_user


def require_category_admin(current_user=Depends(get_current_user)):
    if role_name(current_user) != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can manage categories')
    return current_user


def serialize_keyword(keyword: CategoryKeyword) -> CategoryKeywordResponse:
    return CategoryKeywordResponse(
        id=keyword.id,
        category_id=keyword.category_id,
        keyword=keyword.keyword,
        created_at=keyword.created_at,
    )


def serialize_assignee(user: User) -> CategoryAssigneeResponse:
    return CategoryAssigneeResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=user.role.name if user.role else '',
    )


def serialize_category(category: Category) -> CategoryResponse:
    keywords = [serialize_keyword(keyword) for keyword in category.keywords]
    assigned_users = [
        serialize_assignee(assignment.user)
        for assignment in getattr(category, 'user_assignments', [])
        if assignment.user
    ]
    return CategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        color=category.color,
        sla_hours=category.sla_hours,
        is_active=category.is_active,
        created_by=category.created_by,
        created_at=category.created_at,
        updated_at=category.updated_at,
        keywords=keywords,
        keywords_count=len(keywords),
        assigned_users=assigned_users,
    )


def add_category_audit_log(db: Session, *, action: str, actor_id: UUID, category_id: UUID) -> None:
    AuditService(db).log(
        user_id=actor_id,
        action=action,
        entity_type=CATEGORY_ENTITY_TYPE,
        entity_id=category_id,
        category='CATEGORY_MANAGEMENT',
    )


def replace_keywords(category: Category, keywords: list[str]) -> None:
    category.keywords.clear()
    for keyword in validate_unique_keywords(keywords):
        category.keywords.append(CategoryKeyword(keyword=keyword))


@router.get('', response_model=list[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    current_user=Depends(require_category_access),
) -> list[CategoryResponse]:
    statement = (
        select(Category)
        .options(
            selectinload(Category.keywords),
            selectinload(Category.user_assignments).joinedload(CategoryUserAssignment.user).joinedload(User.role),
        )
        .order_by(Category.created_at.desc())
    )
    return [serialize_category(category) for category in db.scalars(statement)]


@router.post('', response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> CategoryResponse:
    ensure_category_name_available(db, payload.name)
    category = Category(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        sla_hours=payload.sla_hours,
        is_active=True,
        created_by=current_user.id,
    )
    replace_keywords(category, payload.keywords)
    db.add(category)
    db.flush()
    add_category_audit_log(db, action=CategoryAuditActions.CREATED, actor_id=current_user.id, category_id=category.id)
    db.commit()
    db.refresh(category)
    return serialize_category(get_category_or_404(db, category.id))


@router.get('/{category_id}', response_model=CategoryResponse)
def get_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_access),
) -> CategoryResponse:
    return serialize_category(get_category_or_404(db, category_id))


@router.put('/users/{user_id}/assignments', response_model=list[CategoryResponse])
def set_user_category_assignments(
    user_id: UUID,
    payload: UserCategoryAssignmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_assignment_access),
) -> list[CategoryResponse]:
    CategoryAssignmentService(db).set_user_categories(
        user_id=user_id,
        category_ids=payload.category_ids,
        actor_id=current_user.id,
    )
    db.commit()
    statement = (
        select(Category)
        .options(
            selectinload(Category.keywords),
            selectinload(Category.user_assignments).joinedload(CategoryUserAssignment.user).joinedload(User.role),
        )
        .join(CategoryUserAssignment, CategoryUserAssignment.category_id == Category.id)
        .where(CategoryUserAssignment.user_id == user_id)
        .order_by(Category.name.asc())
    )
    return [serialize_category(category) for category in db.scalars(statement)]


@router.put('/{category_id}', response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    payload: CategoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> CategoryResponse:
    category = get_category_or_404(db, category_id)
    ensure_category_name_available(db, payload.name, category_id)
    category.name = payload.name
    category.description = payload.description
    category.color = payload.color
    category.sla_hours = payload.sla_hours
    if payload.is_active is not None:
        category.is_active = payload.is_active
    replace_keywords(category, payload.keywords)
    add_category_audit_log(db, action=CategoryAuditActions.UPDATED, actor_id=current_user.id, category_id=category.id)
    db.commit()
    return serialize_category(get_category_or_404(db, category.id))


@router.patch('/{category_id}/activate', response_model=CategoryResponse)
def activate_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> CategoryResponse:
    category = get_category_or_404(db, category_id)
    category.is_active = True
    add_category_audit_log(db, action=CategoryAuditActions.ACTIVATED, actor_id=current_user.id, category_id=category.id)
    db.commit()
    return serialize_category(get_category_or_404(db, category.id))


@router.patch('/{category_id}/deactivate', response_model=CategoryResponse)
def deactivate_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> CategoryResponse:
    category = get_category_or_404(db, category_id)
    category.is_active = False
    add_category_audit_log(db, action=CategoryAuditActions.DEACTIVATED, actor_id=current_user.id, category_id=category.id)
    db.commit()
    return serialize_category(get_category_or_404(db, category.id))


@router.delete('/{category_id}')
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> dict[str, str]:
    category = get_category_or_404(db, category_id)
    add_category_audit_log(db, action=CategoryAuditActions.DELETED, actor_id=current_user.id, category_id=category.id)
    db.delete(category)
    db.commit()
    return {'message': 'Category deleted successfully'}


@router.post('/{category_id}/keywords', response_model=CategoryKeywordResponse, status_code=status.HTTP_201_CREATED)
def create_category_keyword(
    category_id: UUID,
    payload: CategoryKeywordCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> CategoryKeywordResponse:
    category = get_category_or_404(db, category_id)
    ensure_keyword_available(db, category.id, payload.keyword)
    keyword = CategoryKeyword(category_id=category.id, keyword=payload.keyword)
    db.add(keyword)
    add_category_audit_log(db, action=CategoryAuditActions.KEYWORD_CREATED, actor_id=current_user.id, category_id=category.id)
    db.commit()
    db.refresh(keyword)
    return serialize_keyword(keyword)


@router.delete('/{category_id}/keywords/{keyword_id}')
def delete_category_keyword(
    category_id: UUID,
    keyword_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_category_admin),
) -> dict[str, str]:
    category = get_category_or_404(db, category_id)
    keyword = db.scalar(
        select(CategoryKeyword)
        .where(CategoryKeyword.category_id == category.id)
        .where(CategoryKeyword.id == keyword_id)
    )
    if not keyword:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Keyword not found')

    add_category_audit_log(db, action=CategoryAuditActions.KEYWORD_DELETED, actor_id=current_user.id, category_id=category.id)
    db.delete(keyword)
    db.commit()
    return {'message': 'Keyword deleted successfully'}

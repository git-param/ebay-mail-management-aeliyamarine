from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.schemas.template import (
    PermissionResponse,
    ReplyTemplateCategoryCreateRequest,
    ReplyTemplateCategoryResponse,
    ReplyTemplateCategorySummary,
    ReplyTemplateCategoryUpdateRequest,
    ReplyTemplateCreateRequest,
    ReplyTemplateResponse,
    ReplyTemplateUpdateRequest,
    RolePermissionUpdateRequest,
)
from app.services.permission_service import PermissionService
from app.services.template_service import ReplyTemplateService


router = APIRouter()


def serialize_template(template) -> ReplyTemplateResponse:
    """Convert a template model to its API response."""
    return ReplyTemplateResponse(
        id=template.id,
        title=template.title,
        body=template.body,
        category_id=template.category_id,
        category=serialize_category_summary(template.category) if template.category else None,
        is_active=template.is_active,
        created_by=template.created_by,
        updated_by=template.updated_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def serialize_category_summary(category) -> ReplyTemplateCategorySummary:
    """Convert a template category model to its compact API response."""
    return ReplyTemplateCategorySummary(
        id=category.id,
        name=category.name,
        is_active=category.is_active,
    )


def serialize_category(category) -> ReplyTemplateCategoryResponse:
    """Convert a template category model to its API response."""
    return ReplyTemplateCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        is_active=category.is_active,
        created_by=category.created_by,
        updated_by=category.updated_by,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def serialize_permission(permission) -> PermissionResponse:
    """Convert a permission model to its API response."""
    return PermissionResponse(code=permission.code, description=permission.description)


@router.get('', response_model=list[ReplyTemplateResponse])
def list_templates(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[ReplyTemplateResponse]:
    """List reply templates available for use during replies."""
    PermissionService(db).ensure_user_has(current_user, 'template.view')
    templates = ReplyTemplateService(db).list_templates(include_inactive=include_inactive)
    return [serialize_template(template) for template in templates]


@router.post('', response_model=ReplyTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: ReplyTemplateCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ReplyTemplateResponse:
    """Create a new reply template."""
    PermissionService(db).ensure_user_has(current_user, 'template.create')
    template = ReplyTemplateService(db).create_template(
        title=payload.title,
        body=payload.body,
        category_id=payload.category_id,
        is_active=payload.is_active,
        actor_id=current_user.id,
    )
    return serialize_template(template)


@router.put('/{template_id}', response_model=ReplyTemplateResponse)
def update_template(
    template_id: UUID,
    payload: ReplyTemplateUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ReplyTemplateResponse:
    """Update an existing reply template."""
    PermissionService(db).ensure_user_has(current_user, 'template.edit')
    template = ReplyTemplateService(db).update_template(
        template_id=template_id,
        values=payload.model_dump(exclude_unset=True),
        actor_id=current_user.id,
    )
    return serialize_template(template)


@router.delete('/{template_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Delete a reply template."""
    PermissionService(db).ensure_user_has(current_user, 'template.delete')
    ReplyTemplateService(db).delete_template(template_id=template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/categories', response_model=list[ReplyTemplateCategoryResponse])
def list_template_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[ReplyTemplateCategoryResponse]:
    """List reply template categories."""
    PermissionService(db).ensure_user_has(current_user, 'template.view')
    categories = ReplyTemplateService(db).list_categories(include_inactive=include_inactive)
    return [serialize_category(category) for category in categories]


@router.post('/categories', response_model=ReplyTemplateCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_template_category(
    payload: ReplyTemplateCategoryCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ReplyTemplateCategoryResponse:
    """Create a reply template category."""
    PermissionService(db).ensure_user_has(current_user, 'template.create')
    category = ReplyTemplateService(db).create_category(
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        actor_id=current_user.id,
    )
    return serialize_category(category)


@router.put('/categories/{category_id}', response_model=ReplyTemplateCategoryResponse)
def update_template_category(
    category_id: UUID,
    payload: ReplyTemplateCategoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ReplyTemplateCategoryResponse:
    """Update a reply template category."""
    PermissionService(db).ensure_user_has(current_user, 'template.edit')
    category = ReplyTemplateService(db).update_category(
        category_id=category_id,
        values=payload.model_dump(exclude_unset=True),
        actor_id=current_user.id,
    )
    return serialize_category(category)


@router.delete('/categories/{category_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_template_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Delete a reply template category while keeping its templates."""
    PermissionService(db).ensure_user_has(current_user, 'template.delete')
    ReplyTemplateService(db).delete_category(category_id=category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/roles/{role_id}/permissions', response_model=list[PermissionResponse])
def list_role_permissions(
    role_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> list[PermissionResponse]:
    """List permissions assigned to a role for admin configuration."""
    permissions = PermissionService(db).list_role_permissions(role_id)
    return [serialize_permission(permission) for permission in permissions]


@router.put('/roles/{role_id}/permissions', response_model=list[PermissionResponse])
def update_role_permissions(
    role_id: UUID,
    payload: RolePermissionUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> list[PermissionResponse]:
    """Replace permissions assigned to a role for admin configuration."""
    service = PermissionService(db)
    service.replace_role_permissions(role_id, payload.permission_codes)
    return [serialize_permission(permission) for permission in service.list_role_permissions(role_id)]

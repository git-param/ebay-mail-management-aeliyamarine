from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.schemas.template import (
    PermissionResponse,
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
        is_active=template.is_active,
        created_by=template.created_by,
        updated_by=template.updated_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
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

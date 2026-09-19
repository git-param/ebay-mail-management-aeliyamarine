from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import is_support_agent
from app.models.role import Role
from app.repositories.permission_repository import PermissionRepository


AGENT_TEMPLATE_PERMISSIONS = frozenset({
    'template.view',
    'template.create',
    'template.edit',
})


class PermissionService:
    """Permission checks backed by role-permission rows."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = PermissionRepository(db)

    def ensure_user_has(self, user, permission_code: str) -> None:
        """Raise 403 when the user's role lacks a permission."""
        if is_support_agent(user) and permission_code in AGENT_TEMPLATE_PERMISSIONS:
            return
        if not user.role_id or not self.repository.role_has_permission(user.role_id, permission_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permission')

    def list_role_permissions(self, role_id: UUID):
        """Return permissions assigned to a role."""
        if not self.db.get(Role, role_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Role not found')
        return self.repository.list_role_permissions(role_id)

    def replace_role_permissions(self, role_id: UUID, permission_codes: list[str]) -> None:
        """Replace a role's permission grants."""
        if not self.db.get(Role, role_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Role not found')
        self.repository.replace_role_permissions(role_id, permission_codes)
        self.db.commit()

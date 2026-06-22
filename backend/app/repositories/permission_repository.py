from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.permission import Permission, RolePermission


class PermissionRepository:
    """Data access for permissions and role grants."""

    def __init__(self, db: Session):
        self.db = db

    def role_has_permission(self, role_id: UUID, permission_code: str) -> bool:
        """Return True when a role has the requested permission code."""
        statement = (
            select(RolePermission.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id == role_id)
            .where(Permission.code == permission_code)
        )
        return self.db.scalar(statement) is not None

    def list_role_permissions(self, role_id: UUID) -> list[Permission]:
        """List permissions currently assigned to a role."""
        statement = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.code)
        )
        return list(self.db.scalars(statement))

    def replace_role_permissions(self, role_id: UUID, permission_codes: list[str]) -> None:
        """Replace all permissions assigned to a role with the provided codes."""
        permissions = list(self.db.scalars(select(Permission).where(Permission.code.in_(permission_codes))))
        self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for permission in permissions:
            self.db.add(RolePermission(role_id=role_id, permission_id=permission.id))

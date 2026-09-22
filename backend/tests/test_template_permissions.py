from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.permission_service import PermissionService


def user_with_role(role_name: str):
    return SimpleNamespace(role_id='role-id', role=SimpleNamespace(name=role_name))


class TemplatePermissionTests(TestCase):
    def test_support_agent_can_manage_templates_without_database_grants(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=False)

        for permission_code in ('template.view', 'template.create', 'template.edit'):
            with self.subTest(permission_code=permission_code):
                service.ensure_user_has(user_with_role('Support Agent'), permission_code)

        service.repository.role_has_permission.assert_not_called()

    def test_support_agent_cannot_delete_template_without_database_grant(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=False)

        with self.assertRaises(HTTPException) as context:
            service.ensure_user_has(user_with_role('Support Agent'), 'template.delete')

        self.assertEqual(context.exception.status_code, 403)

    def test_non_agent_template_access_still_uses_database_grants(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=True)
        user = user_with_role('Operations Manager')

        service.ensure_user_has(user, 'template.create')

        service.repository.role_has_permission.assert_called_once_with('role-id', 'template.create')

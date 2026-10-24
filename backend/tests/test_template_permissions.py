from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.permission_service import PermissionService


def user_with_role(role_name: str):
    return SimpleNamespace(role_id='role-id', role=SimpleNamespace(name=role_name))


class TemplatePermissionTests(TestCase):
    def test_support_agent_can_view_templates_without_database_grants(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=False)

        service.ensure_user_has(user_with_role('Support Agent'), 'template.view')

        service.repository.role_has_permission.assert_not_called()

    def test_support_agent_cannot_manage_templates_even_with_database_grants(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=True)

        for permission_code in ('template.create', 'template.edit', 'template.delete'):
            with self.subTest(permission_code=permission_code), self.assertRaises(HTTPException) as context:
                service.ensure_user_has(user_with_role('Support Agent'), permission_code)

            self.assertEqual(context.exception.status_code, 403)
        service.repository.role_has_permission.assert_not_called()

    def test_non_agent_template_access_still_uses_database_grants(self):
        service = PermissionService(Mock())
        service.repository.role_has_permission = Mock(return_value=True)
        user = user_with_role('Operations Manager')

        service.ensure_user_has(user, 'template.create')

        service.repository.role_has_permission.assert_called_once_with('role-id', 'template.create')

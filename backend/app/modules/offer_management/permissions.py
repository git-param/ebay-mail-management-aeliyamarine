from fastapi import HTTPException, status

from app.api.dependencies import can_manage_operations, normalized_role_name


def can_view_all_offer_entries(user) -> bool:
    return can_manage_operations(user)


def require_offer_entry_access(user, entry) -> None:
    if can_view_all_offer_entries(user):
        return
    if str(entry.created_by_user_id) == str(user.id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You can only access offer entries created by you.')


def require_offer_history_access(user) -> None:
    if can_view_all_offer_entries(user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can view offer history.')


def role_label(user) -> str:
    role = normalized_role_name(user)
    if role == 'SUPPORT_AGENT':
        return 'Agent'
    if role == 'OPERATIONS_MANAGER':
        return 'Ops Manager'
    return role.title().replace('_', ' ')


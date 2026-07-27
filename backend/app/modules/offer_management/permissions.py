from fastapi import HTTPException, status

from app.api.dependencies import can_manage_operations, normalized_role_name


def can_view_all_offer_entries(user) -> bool:
    _ = user
    return True


def require_offer_entry_access(user, entry) -> None:
    _ = user
    _ = entry
    return


def require_offer_history_access(user) -> None:
    if can_view_all_offer_entries(user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can view offer history.')


def require_offer_entry_delete_access(user) -> None:
    if can_view_all_offer_entries(user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins and operations managers can delete offer entries.')


def role_label(user) -> str:
    role = normalized_role_name(user)
    if role == 'SUPPORT_AGENT':
        return 'Agent'
    if role == 'OPERATIONS_MANAGER':
        return 'Ops Manager'
    return role.title().replace('_', ' ')

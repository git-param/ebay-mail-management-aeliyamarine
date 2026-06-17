from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.ebay_account import EbayAccount, EbayConnectionStatus
from app.schemas.ebay_account import EbayAccountCreateRequest, EbayAccountResponse, EbayAccountUpdateRequest


router = APIRouter()

EBAY_ACCOUNT_ENTITY_TYPE = 'EBAY_ACCOUNT'


class EbayAccountAuditActions:
    CREATED = 'EBAY_ACCOUNT_CREATED'
    UPDATED = 'EBAY_ACCOUNT_UPDATED'
    ACTIVATED = 'EBAY_ACCOUNT_ACTIVATED'
    DEACTIVATED = 'EBAY_ACCOUNT_DEACTIVATED'
    DELETED = 'EBAY_ACCOUNT_DELETED'


def require_admin(current_user=Depends(get_current_user)):
    if current_user.role.name != 'Admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only admins can manage eBay accounts')
    return current_user


def get_account_or_404(db: Session, account_id: UUID) -> EbayAccount:
    account = db.get(EbayAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBay account not found')
    return account


def serialize_account(account: EbayAccount) -> EbayAccountResponse:
    return EbayAccountResponse(
        id=account.id,
        account_name=account.account_name,
        ebay_username=account.ebay_username,
        environment=account.environment,
        connection_status=account.connection_status,
        is_active=account.is_active,
        oauth_state=account.oauth_state,
        token_expires_at=account.token_expires_at,
        access_token_expires_at=account.access_token_expires_at,
        refresh_token_expires_at=account.refresh_token_expires_at,
        last_connected_at=account.last_connected_at,
        ebay_user_id=account.ebay_user_id,
        store_name=account.store_name,
        last_sync_at=account.last_sync_at,
        sync_status=account.sync_status,
        notes=account.notes,
        created_by=account.created_by,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def add_account_audit_log(db: Session, *, action: str, actor_id: UUID, account_id: UUID) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity_type=EBAY_ACCOUNT_ENTITY_TYPE,
            entity_id=account_id,
        )
    )


@router.get('', response_model=list[EbayAccountResponse])
def list_ebay_accounts(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> list[EbayAccountResponse]:
    statement = select(EbayAccount).order_by(EbayAccount.created_at.desc())
    return [serialize_account(account) for account in db.scalars(statement)]


@router.post('', response_model=EbayAccountResponse, status_code=status.HTTP_201_CREATED)
def create_ebay_account(
    payload: EbayAccountCreateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayAccountResponse:
    account = EbayAccount(
        account_name=payload.account_name.strip(),
        ebay_username=payload.ebay_username.strip(),
        environment=payload.environment,
        connection_status=EbayConnectionStatus.PENDING,
        is_active=True,
        oauth_state=None,
        access_token=None,
        refresh_token=None,
        token_expires_at=None,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        last_connected_at=None,
        ebay_user_id=None,
        store_name=None,
        last_sync_at=None,
        sync_status=None,
        notes=payload.notes.strip() if payload.notes else None,
        created_by=current_user.id,
    )
    db.add(account)
    db.flush()
    add_account_audit_log(
        db,
        action=EbayAccountAuditActions.CREATED,
        actor_id=current_user.id,
        account_id=account.id,
    )
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.get('/{account_id}', response_model=EbayAccountResponse)
def get_ebay_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayAccountResponse:
    return serialize_account(get_account_or_404(db, account_id))


@router.put('/{account_id}', response_model=EbayAccountResponse)
def update_ebay_account(
    account_id: UUID,
    payload: EbayAccountUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayAccountResponse:
    account = get_account_or_404(db, account_id)
    account.account_name = payload.account_name.strip()
    account.ebay_username = payload.ebay_username.strip()
    account.environment = payload.environment
    account.notes = payload.notes.strip() if payload.notes else None
    add_account_audit_log(
        db,
        action=EbayAccountAuditActions.UPDATED,
        actor_id=current_user.id,
        account_id=account.id,
    )
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.patch('/{account_id}/activate', response_model=EbayAccountResponse)
def activate_ebay_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayAccountResponse:
    account = get_account_or_404(db, account_id)
    account.is_active = True
    add_account_audit_log(
        db,
        action=EbayAccountAuditActions.ACTIVATED,
        actor_id=current_user.id,
        account_id=account.id,
    )
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.patch('/{account_id}/deactivate', response_model=EbayAccountResponse)
def deactivate_ebay_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> EbayAccountResponse:
    account = get_account_or_404(db, account_id)
    account.is_active = False
    add_account_audit_log(
        db,
        action=EbayAccountAuditActions.DEACTIVATED,
        actor_id=current_user.id,
        account_id=account.id,
    )
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.delete('/{account_id}')
def delete_ebay_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> dict[str, str]:
    account = get_account_or_404(db, account_id)
    add_account_audit_log(
        db,
        action=EbayAccountAuditActions.DELETED,
        actor_id=current_user.id,
        account_id=account.id,
    )
    db.delete(account)
    db.commit()
    return {'message': 'eBay account deleted successfully'}

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.constants.api import SoldPostingRoutes
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.ebay_account import EbayAccount
from app.modules.sold_posting.models import SoldPostingStatus

VISIBLE_STATUSES = [
    SoldPostingStatus.AWAITING_PAYMENT.value,
    SoldPostingStatus.AWAITING_SHIPMENT.value,
    SoldPostingStatus.SHIPPED.value,
    SoldPostingStatus.DELIVERED.value,
    SoldPostingStatus.CANCELLED.value,
    SoldPostingStatus.REFUNDED.value,
    SoldPostingStatus.OTHER.value,
]
from app.modules.sold_posting.schemas import SoldPostingEditRequest, SoldPostingFilterOptions, SoldPostingListResponse, SoldPostingRow, SoldPostingOrderDetail, SoldPostingSyncResponse
from app.modules.sold_posting.service import SoldPostingService
from app.modules.sold_posting.schemas import OrderBuyerConversationResponse
from app.services.order_buyer_conversation_service import OrderBuyerConversationService


router = APIRouter()


@router.get(SoldPostingRoutes.ORDER_CONVERSATION, response_model=OrderBuyerConversationResponse)
def order_buyer_conversation(
    order_id: str,
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return OrderBuyerConversationService(db).resolve(order_id, account_id)


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()] if value else []


@router.get(SoldPostingRoutes.ORDERS, response_model=SoldPostingListResponse)
def list_orders(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    date_sold_from: date | None = None,
    date_sold_to: date | None = None,
    date_paid_from: date | None = None,
    date_paid_to: date | None = None,
    account_ids: str | None = None,
    statuses: str | None = None,
    sku: str | None = None,
    order_id: str | None = None,
    buyer_username: str | None = None,
    item_id: str | None = None,
    search: str | None = None,
    sort_by: str = 'date_sold',
    sort_direction: str = 'desc',
):
    _ = current_user
    filters = {
        'date_sold_from': date_sold_from,
        'date_sold_to': date_sold_to,
        'date_paid_from': date_paid_from,
        'date_paid_to': date_paid_to,
        'account_ids': [UUID(x) for x in _csv(account_ids)],
        'statuses': _csv(statuses),
        'sku': sku,
        'order_id': order_id,
        'buyer_username': buyer_username,
        'item_id': item_id,
        'search': search,
    }
    return SoldPostingService(db).list_rows(filters, page, page_size, sort_by, sort_direction)


@router.get(SoldPostingRoutes.ORDERS_BY_ORDER_ID, response_model=SoldPostingOrderDetail)
def order_detail(order_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _ = current_user
    order = SoldPostingService(db).detail(order_id)
    return {
        **SoldPostingOrderDetail.model_validate(order).model_dump(exclude={'normalized_status', 'line_items'}),
        'normalized_status': order.normalized_status.value,
        'line_items': order.line_items,
    }


@router.put(SoldPostingRoutes.LINE_ITEMS_BY_LINE_ITEM_RECORD_ID, response_model=SoldPostingRow)
def update_line_item(line_item_record_id: UUID, payload: SoldPostingEditRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _ = current_user
    return SoldPostingService(db).update_line_order_fields(line_item_record_id, payload)


@router.post(SoldPostingRoutes.LINE_ITEMS_BY_LINE_ITEM_RECORD_ID_COPIED, response_model=SoldPostingRow)
def mark_line_item_copied(line_item_record_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return SoldPostingService(db).mark_line_copied(line_item_record_id, current_user.id)


@router.post(SoldPostingRoutes.SYNC, response_model=SoldPostingSyncResponse)
def sync(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = SoldPostingService(db)
    # service.assert_admin_can_sync(current_user)
    return service.sync_all_accounts()


@router.get(SoldPostingRoutes.SYNC_STATUS)
def sync_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _ = current_user
    return SoldPostingService(db).sync_info()


@router.get(SoldPostingRoutes.FILTER_OPTIONS, response_model=SoldPostingFilterOptions)
def filter_options(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    _ = current_user
    accounts = db.query(EbayAccount).filter(EbayAccount.is_active.is_(True)).order_by(EbayAccount.account_name.asc()).all()
    return {
        'accounts': [{'id': str(a.id), 'name': a.account_name or a.store_name or a.ebay_username} for a in accounts],
        'statuses': VISIBLE_STATUSES,
    }

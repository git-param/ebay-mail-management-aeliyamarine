from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.message_type_repository import MessageClassificationRepository


class MessageReportService:
    SORT_FIELDS = {'created_at': 0, 'conversation_id': 1, 'agent': 4, 'category': 5}

    def __init__(self, db: Session): self.db, self.repo = db, MessageClassificationRepository(db)

    @staticmethod
    def bounds(date_from: date | None, date_to: date | None):
        start = datetime.combine(date_from, time.min, tzinfo=UTC) if date_from else None
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC) if date_to else None
        return start, end

    def rows(self, filters, *, limit=None, offset=0, sort_by='created_at', sort_dir='desc'):
        start, end = self.bounds(filters.get('date_from'), filters.get('date_to'))
        query = self.repo.query(date_from=start, date_to=end, **{k: v for k, v in filters.items() if k not in {'date_from','date_to'}})
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        from app.models.message_type import MessageClassification, MessageType
        from app.models.conversation import Conversation
        from app.models.user import User
        sort_column = {'created_at': MessageClassification.created_at, 'conversation_id': Conversation.id,
                       'agent': User.full_name, 'category': MessageType.name}.get(sort_by, MessageClassification.created_at)
        query = query.order_by(sort_column.asc() if sort_dir == 'asc' else sort_column.desc())
        if limit is not None: query = query.offset(offset).limit(limit)
        result = []
        for classification, conversation, message, account, user, leaf, parent in self.db.execute(query):
            category, subcategory = (parent, leaf) if parent else (leaf, None)
            result.append({'id': classification.id, 'created_at': classification.created_at,
                'conversation_id': conversation.id, 'conversation_message_id': message.id,
                'provider_conversation_id': conversation.provider_conversation_id, 'buyer': conversation.buyer_identifier,
                'seller': (account.store_name or account.account_name) if account else None,
                'seller_account_id': classification.seller_account_id, 'user_id': user.id,
                'agent': user.full_name, 'category': category.name, 'category_id': category.id,
                'subcategory': subcategory.name if subcategory else None,
                'subcategory_id': subcategory.id if subcategory else None, 'message_preview': message.body[:240]})
        return result, total

    def report(self, filters, limit, offset, sort_by, sort_dir):
        visible, total = self.rows(filters, limit=limit, offset=offset, sort_by=sort_by, sort_dir=sort_dir)
        all_rows, _ = self.rows(filters)
        def counts(key): return [{'label': k or 'Unknown', 'value': v} for k,v in Counter(row[key] for row in all_rows).most_common()]
        category_counts = counts('category')
        summary = [{'label': 'Total Replies', 'value': total}] + category_counts
        return {'items': visible, 'total': total, 'limit': limit, 'offset': offset, 'summary': summary,
                'messages_per_day': counts('created_at_day') if False else [{'label': k, 'value': v} for k,v in sorted(Counter(row['created_at'].date().isoformat() for row in all_rows).items())],
                'messages_by_employee': counts('agent'), 'messages_by_category': category_counts, 'messages_by_seller_account': counts('seller')}

    def export(self, filters):
        rows, _ = self.rows(filters)
        workbook = Workbook(); sheet = workbook.active; sheet.title = 'Message Report'
        sheet.append(['Date','Time','Conversation ID','Buyer','Seller','Agent','Category','Sub Category','Reply','Reply ID','Created At'])
        for row in rows:
            created = row['created_at']
            sheet.append([created.date().isoformat(), created.time().replace(microsecond=0).isoformat(), str(row['conversation_id']), row['buyer'], row['seller'], row['agent'], row['category'], row['subcategory'], row['message_preview'], str(row['conversation_message_id']), created.isoformat()])
        sheet.freeze_panes = 'A2'; sheet.auto_filter.ref = sheet.dimensions
        stream = BytesIO(); workbook.save(stream); stream.seek(0); return stream

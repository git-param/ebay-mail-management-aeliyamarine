"""Readable event snapshots and best-effort presentation of older audit rows."""
from uuid import UUID
from datetime import timedelta

from sqlalchemy import select

from app.models.category import Category
from app.models.conversation import Conversation, ConversationNote, Message, ConversationCategoryHistory, ConversationAssignment
from app.models.ebay_account import EbayAccount
from app.models.message_type import MessageType
from app.models.user import User


def as_uuid(value):
    try:
        return UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


MODELS = {'USER': User, 'CATEGORY': Category, 'MESSAGE_TYPE': MessageType,
          'EBAY_ACCOUNT': EbayAccount, 'CONVERSATION': Conversation,
          'MESSAGE': Message, 'INTERNAL_NOTE': ConversationNote}
REFERENCE_FIELDS = {
    'user_id': (User, 'user_name'),
    'assigned_by': (User, 'assigned_by_name'),
    'assigned_to': (User, 'assigned_to_name'),
    'previous_assignee': (User, 'previous_assignee_name'),
    'category_id': (Category, 'category_name'),
    'previous_category_id': (Category, 'previous_category_name'),
    'message_type_id': (MessageType, 'message_type_name'),
    'ebay_account_id': (EbayAccount, 'account_name'),
    'provider_account_id': (EbayAccount, 'account_name'),
}


class AuditPresentationService:
    def __init__(self, db):
        self.db = db
        self.cache = {}

    def get(self, model, value):
        identifier = as_uuid(value)
        if not identifier:
            return None
        key = (model, identifier)
        if key not in self.cache:
            self.cache[key] = self.db.get(model, identifier)
        return self.cache[key]

    def preload(self, logs):
        """Batch legacy reference lookups for a page or CSV export."""
        ids = set()
        def collect(value):
            if isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
            elif identifier := as_uuid(value):
                ids.add(identifier)
        for log in logs:
            collect(log.entity_id)
            collect(log.user_id)
            metadata = log.audit_metadata or {}
            for field in [*REFERENCE_FIELDS, 'conversation_id']:
                collect(metadata.get(field))
        if not ids:
            return
        for model in MODELS.values():
            for row in self.db.scalars(select(model).where(model.id.in_(ids))):
                self.cache[(model, row.id)] = row
            for identifier in ids:
                self.cache.setdefault((model, identifier), None)
        conversation_ids = {row.conversation_id for (model, _), row in self.cache.items()
                            if model in {Message, ConversationNote} and row is not None}
        for row in self.db.scalars(select(Conversation).where(Conversation.id.in_(conversation_ids - ids))):
            self.cache[(Conversation, row.id)] = row

    @staticmethod
    def name(record):
        if isinstance(record, User):
            return record.full_name or record.email
        if isinstance(record, EbayAccount):
            return record.account_name or record.ebay_username
        if isinstance(record, Conversation):
            reference = record.provider_conversation_id or str(record.id)
            context = ' · '.join(value for value in [record.subject, record.buyer_identifier] if value)
            return f'Conversation {reference}' + (f' — {context}' if context else '')
        return getattr(record, 'name', None)

    def enrich(self, *, action, user_id, entity_type, entity_id, metadata=None, created_at=None):
        data = dict(metadata or {})
        # Legacy rows can recover exact transitions from their contemporaneous history.
        if created_at and entity_type == 'CONVERSATION' and 'description' not in data:
            if action == 'MESSAGE_CATEGORY_CHANGED' and 'previous_category_id' not in data:
                match = self.db.scalar(select(ConversationCategoryHistory).where(
                    ConversationCategoryHistory.conversation_id == entity_id,
                    ConversationCategoryHistory.changed_by == user_id,
                    ConversationCategoryHistory.new_category_id == as_uuid(data.get('category_id')),
                    ConversationCategoryHistory.changed_at <= created_at,
                    ConversationCategoryHistory.changed_at >= created_at - timedelta(minutes=2))
                    .order_by(ConversationCategoryHistory.changed_at.desc()).limit(1))
                if match:
                    data['previous_category_id'] = str(match.old_category_id) if match.old_category_id else None
            if action == 'CONVERSATION_ASSIGNED' and 'previous_assignee' not in data:
                match = self.db.scalar(select(ConversationAssignment).where(
                    ConversationAssignment.conversation_id == entity_id,
                    ConversationAssignment.assigned_by == user_id,
                    ConversationAssignment.assigned_to == as_uuid(data.get('assigned_to')),
                    ConversationAssignment.assigned_at <= created_at,
                    ConversationAssignment.assigned_at >= created_at - timedelta(minutes=2))
                    .order_by(ConversationAssignment.assigned_at.desc()).limit(1))
                if match:
                    previous = self.db.scalar(select(ConversationAssignment).where(
                        ConversationAssignment.conversation_id == entity_id,
                        ConversationAssignment.assigned_at < match.assigned_at,
                        ConversationAssignment.unassigned_at >= match.assigned_at - timedelta(seconds=2))
                        .order_by(ConversationAssignment.assigned_at.desc()).limit(1))
                    data['previous_assignee'] = str(previous.assigned_to) if previous else None
        actor = self.get(User, user_id)
        if actor:
            data.setdefault('actor_name', self.name(actor))
            data.setdefault('actor_role', actor.role.name if actor.role else '')
        for field, (model, label) in REFERENCE_FIELDS.items():
            if field in data and label not in data:
                value = self.get(model, data[field])
                empty = 'Uncategorized' if model in {Category, MessageType} else 'Unassigned'
                data[label] = self.name(value) if value else (empty if not data[field] else 'Unavailable record')
        model = MODELS.get(entity_type)
        record = self.get(model, entity_id) if model else None
        conversation_id = data.get('conversation_id')
        if entity_type == 'CONVERSATION' and entity_id:
            conversation_id = entity_id
        elif entity_type in {'MESSAGE', 'INTERNAL_NOTE'} and record:
            conversation_id = record.conversation_id
        conversation = self.get(Conversation, conversation_id)
        if conversation_id:
            data.setdefault('conversation_id', str(conversation_id))
        if conversation:
            data.setdefault('conversation_label', self.name(conversation))
        resource = data.get('conversation_label') or (self.name(record) if record else None)
        data.setdefault('resource_label', resource or (entity_type or 'Activity').replace('_', ' ').title())
        data.setdefault('description', self.describe(action, data))
        return data

    @staticmethod
    def describe(action, data):
        actor = data.get('actor_name') or 'System'
        conversation = data.get('conversation_label') or 'the conversation (context unavailable)'
        if action == 'CONVERSATION_ASSIGNED':
            target = data.get('assigned_to_name', 'Unavailable user')
            if 'previous_assignee' in data:
                return f'{actor} assigned {conversation} from {data.get("previous_assignee_name", "Unassigned")} to {target}.'
            return f'{actor} assigned {conversation} to {target}. Previous assignee was not recorded.'
        if action == 'CONVERSATION_UNASSIGNED':
            return f'{actor} unassigned {conversation} from {data.get("previous_assignee_name", "Unavailable user")}.'
        if action == 'MESSAGE_CATEGORY_CHANGED':
            previous = data.get('previous_category_name', 'Previous category not recorded')
            return f'{actor} changed the category of {conversation} from {previous} to {data.get("category_name", "Uncategorized")}.'
        if action == 'MESSAGE_STATUS_CHANGED':
            return f'{actor} changed {conversation} from {data.get("previous_status", "previous status not recorded")} to {data.get("status", "unknown")}.'
        if action == 'MESSAGE_REPLY_SENT':
            return f'{actor} replied in {conversation}.'
        if action == 'REPLY_CATEGORIZED':
            return f'{actor} categorized the reply in {conversation} as {data.get("message_type_name", "Unavailable category")}.'
        if action.startswith('INTERNAL_NOTE_'):
            verb = {'CREATED': 'created', 'UPDATED': 'updated', 'DELETED': 'deleted'}.get(action.rsplit('_', 1)[-1], 'changed')
            return f'{actor} {verb} an internal note in {conversation}.'
        if action == 'LOGIN_SUCCESS':
            method = 'automatically restored their saved session (first login of the day)' if data.get('login_method') == 'cookie' else 'logged in with a password'
            return f'{actor} {method}.'
        if action == 'AUDIT_LOGS_DELETED':
            return f'{actor} deleted {data.get("deleted_count", 0)} audit logs from {data.get("date_from")} through {data.get("date_to")} (India time).'
        if action == 'BULK_ASSIGNMENT_UPDATED':
            return f'{actor} updated {data.get("updated_count", 0)} conversations; {data.get("skipped_count", 0)} skipped. Individual changes are recorded separately.'
        values = []
        for key, value in data.items():
            if key in {'actor_name', 'actor_role', 'resource_label', 'description', 'timestamp'} or key.endswith('_id') or key.endswith('_ids'):
                continue
            if isinstance(value, (str, int, float, bool)) and not as_uuid(value):
                values.append(f'{key.replace("_", " ").capitalize()}: {value}')
        return '; '.join(values) or f'{actor}: {action.replace("_", " ").lower()}.'

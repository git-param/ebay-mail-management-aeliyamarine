from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.message_type import MessageType, MessageTypeKeyword
from app.repositories.message_type_repository import MessageTypeRepository
from app.services.audit_service import AuditService


class MessageTypeService:
    """Manage hierarchical reply classifications and automatic sibling ordering."""
    def __init__(self, db: Session): self.db, self.repo = db, MessageTypeRepository(db)

    def tree(self, include_deleted=False, active_only=False):
        items = self.repo.list(include_deleted)
        if active_only: items = [x for x in items if x.is_active and not x.is_deleted]
        by_parent = {}
        for item in items: by_parent.setdefault(item.parent_id, []).append(item)
        def node(item):
            return {'id': item.id, 'name': item.name, 'parent_id': item.parent_id, 'description': item.description,
                    'display_order': item.display_order, 'is_active': item.is_active, 'is_deleted': item.is_deleted,
                    'created_at': item.created_at, 'updated_at': item.updated_at,
                    'keywords': [keyword.keyword for keyword in item.keywords],
                    'children': [node(child) for child in by_parent.get(item.id, [])]}
        return [node(root) for root in by_parent.get(None, [])]

    def create(self, payload, actor_id):
        """
        Create a message type at the end of its sibling list.

        Args:
            payload: Validated message-type fields supplied by an administrator.
            actor_id: User creating the classification.

        Returns:
            Persisted MessageType instance.

        Side Effects:
            Creates keywords and a business-readable audit event, then commits.

        Business Rules:
            Ordering is system-owned; each new item receives max sibling order + 1.
        """
        if payload.parent_id and not self.repo.get(payload.parent_id): raise HTTPException(422, 'Parent message type not found')
        values = payload.model_dump()
        keywords = values.pop('keywords', [])
        highest_order = self.db.scalar(select(func.max(MessageType.display_order)).where(MessageType.parent_id == payload.parent_id)) or 0
        item = MessageType(**values, display_order=highest_order + 1, created_by=actor_id); self._replace_keywords(item, keywords); self.db.add(item); self.db.flush()
        AuditService(self.db).log(action='MESSAGE_TYPE_CREATED', user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id, metadata={'new': payload.model_dump(mode='json')})
        self.db.commit(); self.db.refresh(item); return item

    def update(self, item_id, payload, actor_id):
        """Update editable classification content without accepting manual ordering."""
        item = self.repo.get(item_id)
        if not item: raise HTTPException(404, 'Message type not found')
        changes = payload.model_dump(exclude_unset=True)
        keywords = changes.pop('keywords', None)
        parent_id = changes.get('parent_id')
        if parent_id and not self.repo.get(parent_id): raise HTTPException(422, 'Parent message type not found')
        if parent_id == item.id or (parent_id and parent_id in self.repo.descendants(item.id)): raise HTTPException(422, 'Circular message type hierarchy is not allowed')
        old = {key: str(getattr(item, key)) if getattr(item, key) is not None else None for key in changes}
        for key, value in changes.items(): setattr(item, key, value)
        if keywords is not None: self._replace_keywords(item, keywords)
        AuditService(self.db).log(action='MESSAGE_TYPE_UPDATED', user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id, metadata={'old': old, 'new': payload.model_dump(mode='json', exclude_unset=True)})
        self.db.commit(); self.db.refresh(item); return item

    def delete(self, item_id, actor_id):
        item = self.repo.get(item_id)
        if not item: raise HTTPException(404, 'Message type not found')
        family_ids = {item_id} | self.repo.descendants(item_id)
        if any(self.repo.used(type_id) for type_id in family_ids): item.is_active = False; action = 'MESSAGE_TYPE_DISABLED'
        else: item.is_deleted = True; item.is_active = False; action = 'MESSAGE_TYPE_DELETED'
        AuditService(self.db).log(action=action, user_id=actor_id, entity_type='MESSAGE_TYPE', entity_id=item.id)
        self.db.commit(); return item
    @staticmethod
    def _clean_keywords(values):
        cleaned = []
        seen = set()
        for value in values or []:
            keyword = ' '.join(value.strip().split())
            normalized = keyword.lower()
            if keyword and normalized not in seen:
                cleaned.append(keyword)
                seen.add(normalized)
        return cleaned

    def _replace_keywords(self, item, values):
        item.keywords.clear()
        item.keywords.extend(MessageTypeKeyword(keyword=value) for value in self._clean_keywords(values))

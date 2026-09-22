from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reply_template import ReplyTemplate, ReplyTemplateCategory


class ReplyTemplateRepository:
    """Data access for reply templates."""

    def __init__(self, db: Session):
        self.db = db

    def list(self, *, include_inactive: bool = False) -> list[ReplyTemplate]:
        """Return templates ordered for selection in the reply composer."""
        statement = select(ReplyTemplate).order_by(ReplyTemplate.title)
        if not include_inactive:
            statement = statement.where(ReplyTemplate.is_active.is_(True))
        return list(self.db.scalars(statement))

    def list_categories(self, *, include_inactive: bool = False) -> list[ReplyTemplateCategory]:
        """Return categories ordered for selection in template management."""
        statement = select(ReplyTemplateCategory).order_by(ReplyTemplateCategory.name)
        if not include_inactive:
            statement = statement.where(ReplyTemplateCategory.is_active.is_(True))
        return list(self.db.scalars(statement))

    def get(self, template_id: UUID) -> ReplyTemplate | None:
        """Return one template by ID."""
        return self.db.get(ReplyTemplate, template_id)

    def get_category(self, category_id: UUID) -> ReplyTemplateCategory | None:
        """Return one template category by ID."""
        return self.db.get(ReplyTemplateCategory, category_id)

    def get_category_by_name(self, name: str) -> ReplyTemplateCategory | None:
        """Return one template category by normalized name."""
        statement = select(ReplyTemplateCategory).where(ReplyTemplateCategory.name.ilike(name))
        return self.db.scalars(statement).first()

    def add(self, template: ReplyTemplate) -> ReplyTemplate:
        """Stage a new template for insertion."""
        self.db.add(template)
        return template

    def add_category(self, category: ReplyTemplateCategory) -> ReplyTemplateCategory:
        """Stage a new template category for insertion."""
        self.db.add(category)
        return category

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reply_template import ReplyTemplate


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

    def get(self, template_id: UUID) -> ReplyTemplate | None:
        """Return one template by ID."""
        return self.db.get(ReplyTemplate, template_id)

    def add(self, template: ReplyTemplate) -> ReplyTemplate:
        """Stage a new template for insertion."""
        self.db.add(template)
        return template

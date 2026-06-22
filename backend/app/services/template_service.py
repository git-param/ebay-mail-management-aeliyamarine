from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.reply_template import ReplyTemplate
from app.repositories.template_repository import ReplyTemplateRepository


class ReplyTemplateService:
    """Business logic for template CRUD operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReplyTemplateRepository(db)

    def list_templates(self, *, include_inactive: bool = False) -> list[ReplyTemplate]:
        """List templates available to the caller."""
        return self.repository.list(include_inactive=include_inactive)

    def create_template(self, *, title: str, body: str, is_active: bool, actor_id: UUID) -> ReplyTemplate:
        """Create a reply template."""
        template = self.repository.add(
            ReplyTemplate(
                title=title.strip(),
                body=body.strip(),
                is_active=is_active,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        self.db.commit()
        self.db.refresh(template)
        return template

    def update_template(self, *, template_id: UUID, values: dict, actor_id: UUID) -> ReplyTemplate:
        """Update a reply template."""
        template = self.repository.get(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Template not found')
        for key, value in values.items():
            if value is not None:
                setattr(template, key, value.strip() if isinstance(value, str) else value)
        template.updated_by = actor_id
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, *, template_id: UUID) -> None:
        """Delete a reply template."""
        template = self.repository.get(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Template not found')
        self.db.delete(template)
        self.db.commit()

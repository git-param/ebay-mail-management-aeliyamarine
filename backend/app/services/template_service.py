from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.reply_template import ReplyTemplate, ReplyTemplateCategory
from app.repositories.template_repository import ReplyTemplateRepository


class ReplyTemplateService:
    """Business logic for template CRUD operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReplyTemplateRepository(db)

    def list_templates(self, *, include_inactive: bool = False) -> list[ReplyTemplate]:
        """List templates available to the caller."""
        return self.repository.list(include_inactive=include_inactive)

    def list_categories(self, *, include_inactive: bool = False) -> list[ReplyTemplateCategory]:
        """List template categories available to the caller."""
        return self.repository.list_categories(include_inactive=include_inactive)

    def create_template(
        self,
        *,
        title: str,
        body: str,
        category_id: UUID | None,
        is_active: bool,
        actor_id: UUID,
    ) -> ReplyTemplate:
        """Create a reply template."""
        self._ensure_category_exists(category_id)
        template = self.repository.add(
            ReplyTemplate(
                title=title.strip(),
                body=body.strip(),
                category_id=category_id,
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
            if key == 'category_id':
                self._ensure_category_exists(value)
                template.category_id = value
            elif value is not None:
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

    def create_category(
        self,
        *,
        name: str,
        description: str | None,
        is_active: bool,
        actor_id: UUID,
    ) -> ReplyTemplateCategory:
        """Create a template category."""
        self._ensure_unique_category_name(name)
        category = self.repository.add_category(
            ReplyTemplateCategory(
                name=name.strip(),
                description=description.strip() if description else None,
                is_active=is_active,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        self.db.commit()
        self.db.refresh(category)
        return category

    def update_category(self, *, category_id: UUID, values: dict, actor_id: UUID) -> ReplyTemplateCategory:
        """Update a template category."""
        category = self.repository.get_category(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Template category not found')

        if 'name' in values and values['name'] is not None:
            self._ensure_unique_category_name(values['name'], category_id=category_id)

        for key, value in values.items():
            if key == 'description':
                category.description = value.strip() if value else None
            elif value is not None:
                setattr(category, key, value.strip() if isinstance(value, str) else value)

        category.updated_by = actor_id
        self.db.commit()
        self.db.refresh(category)
        return category

    def delete_category(self, *, category_id: UUID) -> None:
        """Delete a template category and leave its templates uncategorized."""
        category = self.repository.get_category(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Template category not found')
        self.db.delete(category)
        self.db.commit()

    def _ensure_category_exists(self, category_id: UUID | None) -> None:
        if category_id is None:
            return
        if not self.repository.get_category(category_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Template category not found')

    def _ensure_unique_category_name(self, name: str, category_id: UUID | None = None) -> None:
        existing = self.repository.get_category_by_name(name.strip())
        if existing and existing.id != category_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Template category name already exists')

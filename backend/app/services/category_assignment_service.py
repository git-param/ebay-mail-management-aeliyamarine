from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category, CategoryUserAssignment
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


class CategoryAssignmentService:
    def __init__(self, db: Session):
        self.db = db

    def assigned_category_ids(self, user_id: UUID) -> set[UUID]:
        return set(
            self.db.scalars(
                select(CategoryUserAssignment.category_id).where(CategoryUserAssignment.user_id == user_id)
            )
        )

    def users_for_category(self, category_id: UUID) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .join(CategoryUserAssignment, CategoryUserAssignment.user_id == User.id)
                .where(CategoryUserAssignment.category_id == category_id)
                .where(User.is_active.is_(True))
            )
        )

    def set_user_categories(self, *, user_id: UUID, category_ids: list[UUID], actor_id: UUID) -> list[Category]:
        user = self.db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

        unique_category_ids = list(dict.fromkeys(category_ids))
        categories = list(
            self.db.scalars(
                select(Category)
                .options(selectinload(Category.keywords))
                .where(Category.id.in_(unique_category_ids))
            )
        ) if unique_category_ids else []
        found_ids = {category.id for category in categories}
        missing_ids = [category_id for category_id in unique_category_ids if category_id not in found_ids]
        if missing_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='One or more categories were not found')

        previous_ids = self.assigned_category_ids(user_id)
        self.db.execute(delete(CategoryUserAssignment).where(CategoryUserAssignment.user_id == user_id))
        for category_id in unique_category_ids:
            self.db.add(CategoryUserAssignment(category_id=category_id, user_id=user_id, assigned_by=actor_id))

        next_ids = set(unique_category_ids)
        AuditService(self.db).log(
            action='CATEGORY_ASSIGNMENTS_UPDATED',
            user_id=actor_id,
            entity_type='USER',
            entity_id=user_id,
            category='CATEGORY_MANAGEMENT',
            metadata={
                'previous_category_ids': [str(value) for value in previous_ids],
                'category_ids': [str(value) for value in next_ids],
            },
        )
        NotificationService(self.db).create(
            user_id=user_id,
            title='Category access updated',
            body='Your assigned support categories were updated.',
            event_type='CATEGORY_ASSIGNMENT',
            event_key=f'category-assignment:{user_id}:{sorted(str(value) for value in next_ids)}',
            resource_type='USER',
            resource_id=user_id,
        )
        return categories

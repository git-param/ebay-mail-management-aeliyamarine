from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import User
from app.modules.task_management.models import AssignmentTargetType, Subtask, SubtaskSourceType, TaskCategory, TaskStatus, UserSubtaskAssignment
from app.modules.task_management.schemas import AssignmentPayload, CategoryAssignmentPayload, TaskCategoryPayload, SubtaskPayload
from app.services.audit_service import AuditService


class TaskManagementService:
    def __init__(self, db: Session):
        self.db = db

    def list_categories(self) -> list[TaskCategory]:
        return list(self.db.scalars(
            select(TaskCategory)
            .options(selectinload(TaskCategory.subtasks).selectinload(Subtask.assignments))
            .order_by(TaskCategory.display_order.asc(), TaskCategory.name.asc())
        ))

    def save_category(self, payload: TaskCategoryPayload, actor: User, category_id: UUID | None = None) -> TaskCategory:
        category = self.db.get(TaskCategory, category_id) if category_id else TaskCategory(created_by_user_id=actor.id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        category.name = payload.name.strip()
        category.description = payload.description
        category.status = self._enum(TaskStatus, payload.status, 'Invalid task category status')
        category.quality_weight = payload.quality_weight
        category.display_order = payload.display_order
        category.updated_by_user_id = actor.id
        self.db.add(category)
        self.db.flush()
        self._audit('TASK_CATEGORY_UPDATED' if category_id else 'TASK_CATEGORY_CREATED', actor, 'TASK_CATEGORY', category.id, {'name': category.name, 'status': category.status.value})
        self.db.commit()
        self.db.refresh(category)
        return category

    def save_subtask(self, payload: SubtaskPayload, actor: User, subtask_id: UUID | None = None) -> Subtask:
        category = self.db.get(TaskCategory, payload.task_category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        subtask = self.db.get(Subtask, subtask_id) if subtask_id else Subtask(created_by_user_id=actor.id)
        if not subtask:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subtask not found')
        subtask.task_category_id = category.id
        subtask.name = payload.name.strip()
        subtask.description = payload.description
        subtask.status = self._enum(TaskStatus, payload.status, 'Invalid subtask status')
        subtask.display_order = payload.display_order
        subtask.source_type = self._enum(SubtaskSourceType, payload.source_type, 'Invalid source type')
        subtask.source_reference_id = payload.source_reference_id
        subtask.source_configuration = payload.source_configuration
        subtask.count_method = payload.count_method
        subtask.completion_rule = payload.completion_rule
        subtask.supports_automatic_fetch = payload.supports_automatic_fetch
        subtask.updated_by_user_id = actor.id
        self.db.add(subtask)
        self.db.flush()
        self._audit('SUBTASK_UPDATED' if subtask_id else 'SUBTASK_CREATED', actor, 'SUBTASK', subtask.id, {'name': subtask.name, 'source_type': subtask.source_type.value})
        self.db.commit()
        self.db.refresh(subtask)
        return subtask

    def list_assignments(self, user_id: UUID | None = None) -> list[UserSubtaskAssignment]:
        statement = (
            select(UserSubtaskAssignment)
            .options(selectinload(UserSubtaskAssignment.subtask).selectinload(Subtask.category))
            .order_by(UserSubtaskAssignment.display_order.asc(), UserSubtaskAssignment.created_at.asc())
        )
        if user_id:
            statement = statement.where(UserSubtaskAssignment.user_id == user_id)
        return list(self.db.scalars(statement))

    def save_assignment(self, payload: AssignmentPayload, actor: User, assignment_id: UUID | None = None) -> UserSubtaskAssignment:
        user = self.db.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        subtask = self.db.get(Subtask, payload.subtask_id)
        if not subtask:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subtask not found')
        if payload.effective_to and payload.effective_to < payload.effective_from:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Effective To cannot be before Effective From')
        assignment = self.db.get(UserSubtaskAssignment, assignment_id) if assignment_id else self._existing_assignment(user.id, subtask.id, payload.effective_from)
        if assignment_id and not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task assignment not found')
        is_update = bool(assignment)
        if not assignment:
            assignment = UserSubtaskAssignment(created_by_user_id=actor.id)
        self._apply_assignment_payload(assignment, user.id, subtask.id, payload, actor)
        self._validate_user_weight(user.id)
        self._audit('TASK_ASSIGNMENT_UPDATED' if is_update else 'TASK_ASSIGNMENT_CREATED', actor, 'USER_SUBTASK_ASSIGNMENT', assignment.id, {'user_id': str(user.id), 'subtask_id': str(subtask.id), 'quality_weight': float(assignment.quality_weight)})
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def save_category_assignment(self, payload: CategoryAssignmentPayload, actor: User) -> None:
        user = self.db.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        category = self.db.get(TaskCategory, payload.task_category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        if payload.effective_to and payload.effective_to < payload.effective_from:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Effective To cannot be before Effective From')

        subtasks = list(self.db.scalars(
            select(Subtask)
            .where(Subtask.task_category_id == category.id, Subtask.status == TaskStatus.ACTIVE)
            .order_by(Subtask.display_order.asc(), Subtask.name.asc())
        ))
        if not subtasks:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Add at least one active subtask before assigning this task.')

        category_weight = float(category.quality_weight or 0)
        split_weights = self._split_weight(category_weight, len(subtasks))
        target_type = self._enum(AssignmentTargetType, payload.target_type, 'Invalid target type')
        assignment_status = self._enum(TaskStatus, payload.status, 'Invalid assignment status')
        changed_ids: list[str] = []

        for index, subtask in enumerate(subtasks):
            assignment = self._existing_assignment(user.id, subtask.id, payload.effective_from) or self._existing_active_assignment(user.id, subtask.id)
            if not assignment:
                assignment = UserSubtaskAssignment(created_by_user_id=actor.id)
            assignment.user_id = user.id
            assignment.subtask_id = subtask.id
            assignment.quality_weight = split_weights[index]
            assignment.effective_from = payload.effective_from
            assignment.effective_to = payload.effective_to
            assignment.auto_fetch_enabled = payload.auto_fetch_enabled
            assignment.target_type = target_type
            assignment.target_value = payload.target_value
            assignment.display_order = payload.display_order + index
            assignment.status = assignment_status
            assignment.updated_by_user_id = actor.id
            self.db.add(assignment)
            self.db.flush()
            changed_ids.append(str(assignment.id))

        self._validate_user_weight(user.id)
        self._audit('TASK_CATEGORY_ASSIGNED', actor, 'TASK_CATEGORY', category.id, {
            'user_id': str(user.id),
            'quality_weight': category_weight,
            'subtask_count': len(subtasks),
            'assignment_ids': changed_ids,
        })
        self.db.commit()

    def active_weight_total(self, user_id: UUID) -> float:
        total = self.db.scalar(select(func.coalesce(func.sum(UserSubtaskAssignment.quality_weight), 0)).where(
            UserSubtaskAssignment.user_id == user_id,
            UserSubtaskAssignment.status == TaskStatus.ACTIVE,
        ))
        return float(total or 0)

    def _validate_user_weight(self, user_id: UUID) -> None:
        statement = select(func.coalesce(func.sum(UserSubtaskAssignment.quality_weight), 0)).where(
            UserSubtaskAssignment.user_id == user_id,
            UserSubtaskAssignment.status == TaskStatus.ACTIVE,
        )
        total = float(self.db.scalar(statement) or 0)
        if total > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Active task assignment weights cannot exceed 100.')

    def _existing_assignment(self, user_id: UUID, subtask_id: UUID, effective_from) -> UserSubtaskAssignment | None:
        return self.db.scalar(select(UserSubtaskAssignment).where(
            UserSubtaskAssignment.user_id == user_id,
            UserSubtaskAssignment.subtask_id == subtask_id,
            UserSubtaskAssignment.effective_from == effective_from,
        ))

    def _existing_active_assignment(self, user_id: UUID, subtask_id: UUID) -> UserSubtaskAssignment | None:
        return self.db.scalar(
            select(UserSubtaskAssignment)
            .where(
                UserSubtaskAssignment.user_id == user_id,
                UserSubtaskAssignment.subtask_id == subtask_id,
                UserSubtaskAssignment.status == TaskStatus.ACTIVE,
                UserSubtaskAssignment.effective_to.is_(None),
            )
            .order_by(UserSubtaskAssignment.created_at.desc())
        )

    def _apply_assignment_payload(self, assignment: UserSubtaskAssignment, user_id: UUID, subtask_id: UUID, payload: AssignmentPayload, actor: User) -> None:
        assignment.user_id = user_id
        assignment.subtask_id = subtask_id
        assignment.quality_weight = payload.quality_weight
        assignment.effective_from = payload.effective_from
        assignment.effective_to = payload.effective_to
        assignment.auto_fetch_enabled = payload.auto_fetch_enabled
        assignment.target_type = self._enum(AssignmentTargetType, payload.target_type, 'Invalid target type')
        assignment.target_value = payload.target_value
        assignment.display_order = payload.display_order
        assignment.status = self._enum(TaskStatus, payload.status, 'Invalid assignment status')
        assignment.updated_by_user_id = actor.id
        self.db.add(assignment)
        self.db.flush()

    def _split_weight(self, total: float, count: int) -> list[float]:
        base = round(float(total) / count, 2)
        weights = [base for _ in range(count)]
        weights[-1] = round(float(total) - sum(weights[:-1]), 2)
        return weights

    def _enum(self, enum_cls, value: str, error: str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error) from exc

    def _audit(self, action: str, actor: User, entity_type: str, entity_id: UUID, metadata: dict) -> None:
        AuditService(self.db).log(action=action, user_id=actor.id, entity_type=entity_type, entity_id=entity_id, category='TASK_MANAGEMENT', metadata=metadata)

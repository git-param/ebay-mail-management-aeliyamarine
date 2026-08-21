from uuid import UUID
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.user import User
from app.modules.task_management.models import SubSubtask, Subtask, SubtaskSourceType, TaskCategory, TaskStatus, UserSubtaskAssignment
from app.modules.task_management.schemas import AssignmentPayload, TaskAssignmentPayload, TaskCategoryPayload, SubSubtaskPayload, SubtaskPayload
from app.services.audit_service import AuditService


class TaskManagementService:
    def __init__(self, db: Session):
        self.db = db

    def list_categories(self) -> list[TaskCategory]:
        return list(self.db.scalars(
            select(TaskCategory)
            .options(
                selectinload(TaskCategory.subtasks).selectinload(Subtask.assignments),
                selectinload(TaskCategory.subtasks).selectinload(Subtask.child_tasks).selectinload(SubSubtask.assignments),
            )
            .order_by(TaskCategory.display_order.asc(), TaskCategory.name.asc())
        ))

    def save_category(self, payload: TaskCategoryPayload, actor: User, category_id: UUID | None = None) -> TaskCategory:
        category = self.db.get(TaskCategory, category_id) if category_id else TaskCategory(created_by_user_id=actor.id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        is_new = category_id is None
        category.name = payload.name.strip()
        category.description = payload.description
        category.status = self._enum(TaskStatus, payload.status, 'Invalid task category status')
        category.quality_weight = payload.quality_weight
        if is_new:
            category.display_order = self._next_category_display_order()
        category.updated_by_user_id = actor.id
        self.db.add(category)
        self.db.flush()
        if is_new:
            self._ensure_default_other_subtask(category, actor)
            self.db.flush()
        self._audit('TASK_CATEGORY_UPDATED' if category_id else 'TASK_CATEGORY_CREATED', actor, 'TASK_CATEGORY', category.id, {'name': category.name, 'status': category.status.value})
        self.db.commit()
        self.db.refresh(category)
        return category

    def delete_category(self, category_id: UUID, actor: User) -> None:
        category = self.db.get(TaskCategory, category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        self.db.delete(category)
        self._audit('TASK_CATEGORY_DELETED', actor, 'TASK_CATEGORY', category.id, {'name': category.name})
        self.db.commit()

    def save_subtask(self, payload: SubtaskPayload, actor: User, subtask_id: UUID | None = None) -> Subtask:
        category = self.db.get(TaskCategory, payload.task_category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        subtask = self.db.get(Subtask, subtask_id) if subtask_id else Subtask(created_by_user_id=actor.id)
        if not subtask:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subtask not found')
        normalized_name = payload.name.strip()
        source_type = self._enum(SubtaskSourceType, payload.source_type, 'Invalid source type')
        if source_type == SubtaskSourceType.MESSAGE_TYPE and not payload.source_reference_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select a Message Type for this subtask')
        other_subtask = self.db.scalar(select(Subtask).where(
            Subtask.task_category_id == category.id,
            func.lower(func.trim(Subtask.name)) == 'other',
            Subtask.id != subtask.id if subtask_id else True,
        ))
        if normalized_name.casefold() == 'other' and other_subtask:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Only one "Other" subtask is allowed for each task')
        subtask.task_category_id = category.id
        subtask.name = normalized_name
        subtask.description = payload.description
        subtask.status = self._enum(TaskStatus, payload.status, 'Invalid subtask status')
        if subtask_id is None:
            subtask.display_order = self._next_subtask_display_order(category.id)
        subtask.source_type = source_type
        subtask.source_reference_id = payload.source_reference_id if source_type == SubtaskSourceType.MESSAGE_TYPE else None
        subtask.source_configuration = payload.source_configuration
        subtask.count_method = payload.count_method
        subtask.completion_rule = payload.completion_rule
        subtask.supports_automatic_fetch = source_type in (
            SubtaskSourceType.MESSAGE_TYPE,
            SubtaskSourceType.SOLD_POSTING,
            SubtaskSourceType.OFFER_MANAGEMENT,
        )
        subtask.updated_by_user_id = actor.id
        self.db.add(subtask)
        self.db.flush()
        self._audit('SUBTASK_UPDATED' if subtask_id else 'SUBTASK_CREATED', actor, 'SUBTASK', subtask.id, {'name': subtask.name, 'source_type': subtask.source_type.value})
        self.db.commit()
        self.db.refresh(subtask)
        return subtask

    def delete_subtask(self, subtask_id: UUID, actor: User) -> None:
        subtask = self.db.get(Subtask, subtask_id)
        if not subtask:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subtask not found')
        self.db.delete(subtask)
        self._audit('SUBTASK_DELETED', actor, 'SUBTASK', subtask.id, {'name': subtask.name})
        self.db.commit()

    def save_sub_subtask(self, payload: SubSubtaskPayload, actor: User, sub_subtask_id: UUID | None = None) -> SubSubtask:
        subtask = self.db.get(Subtask, payload.subtask_id)
        if not subtask:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subtask not found')
        child = self.db.get(SubSubtask, sub_subtask_id) if sub_subtask_id else SubSubtask(created_by_user_id=actor.id)
        if not child:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sub-subtask not found')
        if sub_subtask_id and child.subtask_id != subtask.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Parent subtask cannot be changed for an existing sub-subtask')
        source_type = self._enum(SubtaskSourceType, payload.source_type, 'Invalid source type')
        if source_type == SubtaskSourceType.MESSAGE_TYPE and not payload.source_reference_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select a Message Type for this sub-subtask')
        child.subtask_id = subtask.id
        child.name = payload.name.strip()
        child.description = payload.description
        child.status = self._enum(TaskStatus, payload.status, 'Invalid sub-subtask status')
        if sub_subtask_id is None:
            child.display_order = self._next_sub_subtask_display_order(subtask.id)
        child.source_type = source_type
        child.source_reference_id = payload.source_reference_id if source_type == SubtaskSourceType.MESSAGE_TYPE else None
        child.source_configuration = payload.source_configuration
        child.count_method = payload.count_method
        child.completion_rule = payload.completion_rule
        child.supports_automatic_fetch = source_type in (
            SubtaskSourceType.MESSAGE_TYPE,
            SubtaskSourceType.SOLD_POSTING,
            SubtaskSourceType.OFFER_MANAGEMENT,
        )
        child.updated_by_user_id = actor.id
        self.db.add(child)
        self.db.flush()
        self._audit('SUB_SUBTASK_UPDATED' if sub_subtask_id else 'SUB_SUBTASK_CREATED', actor, 'SUB_SUBTASK', child.id, {'name': child.name, 'source_type': child.source_type.value})
        self.db.commit()
        self.db.refresh(child)
        return child

    def delete_sub_subtask(self, sub_subtask_id: UUID, actor: User) -> None:
        child = self.db.get(SubSubtask, sub_subtask_id)
        if not child:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sub-subtask not found')
        self.db.delete(child)
        self._audit('SUB_SUBTASK_DELETED', actor, 'SUB_SUBTASK', child.id, {'name': child.name})
        self.db.commit()

    def list_assignments(self, user_id: UUID | None = None, as_of: date | None = None) -> list[UserSubtaskAssignment]:
        as_of = as_of or date.today()
        statement = (
            select(UserSubtaskAssignment)
            .options(
                selectinload(UserSubtaskAssignment.subtask).selectinload(Subtask.category),
                selectinload(UserSubtaskAssignment.sub_subtask),
            )
            .order_by(UserSubtaskAssignment.display_order.asc(), UserSubtaskAssignment.created_at.asc())
        )
        statement = statement.where(self._current_assignment_clause(as_of))
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
        sub_subtask = self.db.get(SubSubtask, payload.sub_subtask_id) if payload.sub_subtask_id else None
        if payload.sub_subtask_id and (not sub_subtask or sub_subtask.subtask_id != subtask.id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Sub-subtask does not belong to the selected subtask')
        if payload.effective_to and payload.effective_to < payload.effective_from:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Effective To cannot be before Effective From')
        assignment = self.db.get(UserSubtaskAssignment, assignment_id) if assignment_id else self._existing_assignment(user.id, subtask.id, payload.sub_subtask_id, payload.effective_from)
        if assignment_id and not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task assignment not found')
        is_update = bool(assignment)
        if not assignment:
            assignment = UserSubtaskAssignment(created_by_user_id=actor.id)
        self._apply_assignment_payload(assignment, user.id, subtask.id, payload.sub_subtask_id, payload, actor)
        self._audit('TASK_ASSIGNMENT_UPDATED' if is_update else 'TASK_ASSIGNMENT_CREATED', actor, 'USER_SUBTASK_ASSIGNMENT', assignment.id, {'user_id': str(user.id), 'subtask_id': str(subtask.id), 'quality_weight': float(assignment.quality_weight)})
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def save_task_assignment(self, payload: TaskAssignmentPayload, actor: User) -> list[UserSubtaskAssignment]:
        """Assign every subtask listed under one task/category to a single agent in one transaction."""
        user = self.db.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
        category = self.db.get(TaskCategory, payload.task_category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task category not found')
        if payload.effective_to and payload.effective_to < payload.effective_from:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Effective To cannot be before Effective From')

        active_subtasks = self._active_subtasks_for_category(category)
        if not active_subtasks:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Selected task has no active subtasks to assign')

        active_subtask_ids = {subtask.id for subtask in active_subtasks}
        requested_subtask_ids = [entry.subtask_id for entry in payload.subtask_weights]
        if any(entry.sub_subtask_id for entry in payload.subtask_weights):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Assign marks to subtasks only; sub-subtask marks are split automatically')
        if set(requested_subtask_ids) - active_subtask_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='One or more subtasks do not belong to the selected task')
        if len(set(requested_subtask_ids)) != len(active_subtask_ids) or len(requested_subtask_ids) != len(active_subtask_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Assign every active subtask for the selected task')
        weight_by_subtask_id = {entry.subtask_id: entry.quality_weight for entry in payload.subtask_weights}
        assignment_targets = self._distributed_assignment_targets(active_subtasks, weight_by_subtask_id)
        active_target_keys = {self._target_key(subtask.id, child.id if child else None) for subtask, child, _ in assignment_targets}

        assignment_status = self._enum(TaskStatus, payload.status, 'Invalid assignment status')
        current_assignments = list(self.db.scalars(
            select(UserSubtaskAssignment)
            .options(selectinload(UserSubtaskAssignment.subtask).selectinload(Subtask.category), selectinload(UserSubtaskAssignment.sub_subtask))
            .where(UserSubtaskAssignment.user_id == user.id)
            .where(self._current_assignment_clause(payload.effective_from))
        ))
        current_by_target_key = {self._target_key(assignment.subtask_id, assignment.sub_subtask_id): assignment for assignment in current_assignments}

        results: list[UserSubtaskAssignment] = []
        for index, (subtask, child, quality_weight) in enumerate(assignment_targets):
            sub_subtask_id = child.id if child else None
            key = self._target_key(subtask.id, sub_subtask_id)
            assignment = current_by_target_key.get(key) or self._existing_assignment(user.id, subtask.id, sub_subtask_id, payload.effective_from)
            if not assignment:
                assignment = UserSubtaskAssignment(created_by_user_id=actor.id)
            assignment.user_id = user.id
            assignment.subtask_id = subtask.id
            assignment.sub_subtask_id = sub_subtask_id
            assignment.quality_weight = quality_weight
            assignment.effective_from = payload.effective_from
            assignment.effective_to = payload.effective_to
            assignment.auto_fetch_enabled = payload.auto_fetch_enabled
            assignment.display_order = index
            assignment.status = assignment_status
            assignment.updated_by_user_id = actor.id
            self.db.add(assignment)
            self.db.flush()
            results.append(assignment)

        for assignment in current_assignments:
            if self._target_key(assignment.subtask_id, assignment.sub_subtask_id) in active_target_keys:
                continue
            if assignment.effective_from < payload.effective_from:
                assignment.effective_to = payload.effective_from - timedelta(days=1)
                assignment.status = TaskStatus.INACTIVE
                assignment.updated_by_user_id = actor.id
                self.db.add(assignment)
            else:
                self.db.delete(assignment)

        self._audit('TASK_ASSIGNED_BULK', actor, 'TASK_CATEGORY', category.id, {
            'user_id': str(user.id),
            'task_category_id': str(category.id),
            'subtask_count': len(results),
            'assignment_ids': [str(item.id) for item in results],
        })
        self.db.commit()
        for item in results:
            self.db.refresh(item)
        return results

    def active_weight_total(self, user_id: UUID, as_of: date | None = None) -> float:
        total = self.db.scalar(select(func.coalesce(func.sum(UserSubtaskAssignment.quality_weight), 0)).where(
            UserSubtaskAssignment.user_id == user_id,
            self._current_assignment_clause(as_of or date.today()),
        ))
        return float(total or 0)


    def _existing_assignment(self, user_id: UUID, subtask_id: UUID, sub_subtask_id: UUID | None, effective_from) -> UserSubtaskAssignment | None:
        return self.db.scalar(select(UserSubtaskAssignment).where(
            UserSubtaskAssignment.user_id == user_id,
            UserSubtaskAssignment.subtask_id == subtask_id,
            UserSubtaskAssignment.sub_subtask_id == sub_subtask_id,
            UserSubtaskAssignment.effective_from == effective_from,
        ))

    def _apply_assignment_payload(self, assignment: UserSubtaskAssignment, user_id: UUID, subtask_id: UUID, sub_subtask_id: UUID | None, payload: AssignmentPayload, actor: User) -> None:
        assignment.user_id = user_id
        assignment.subtask_id = subtask_id
        assignment.sub_subtask_id = sub_subtask_id
        assignment.quality_weight = payload.quality_weight
        assignment.effective_from = payload.effective_from
        assignment.effective_to = payload.effective_to
        assignment.auto_fetch_enabled = payload.auto_fetch_enabled
        assignment.status = self._enum(TaskStatus, payload.status, 'Invalid assignment status')
        assignment.updated_by_user_id = actor.id
        self.db.add(assignment)
        self.db.flush()

    def _current_assignment_clause(self, as_of: date):
        return and_(
            UserSubtaskAssignment.status == TaskStatus.ACTIVE,
            UserSubtaskAssignment.effective_from <= as_of,
            or_(UserSubtaskAssignment.effective_to.is_(None), UserSubtaskAssignment.effective_to >= as_of),
        )

    def _next_category_display_order(self) -> int:
        current_max = self.db.scalar(select(func.coalesce(func.max(TaskCategory.display_order), -1)))
        return int(current_max or -1) + 1

    def _next_subtask_display_order(self, category_id: UUID) -> int:
        current_max = self.db.scalar(select(func.coalesce(func.max(Subtask.display_order), -1)).where(Subtask.task_category_id == category_id))
        return int(current_max or -1) + 1

    def _next_sub_subtask_display_order(self, subtask_id: UUID) -> int:
        current_max = self.db.scalar(select(func.coalesce(func.max(SubSubtask.display_order), -1)).where(SubSubtask.subtask_id == subtask_id))
        return int(current_max or -1) + 1

    def _active_subtasks_for_category(self, category: TaskCategory) -> list[Subtask]:
        return [
            subtask
            for subtask in sorted(category.subtasks, key=lambda item: (item.display_order, item.name))
            if subtask.status == TaskStatus.ACTIVE
        ]

    def _distributed_assignment_targets(self, subtasks: list[Subtask], weight_by_subtask_id: dict[UUID, float]) -> list[tuple[Subtask, SubSubtask | None, float]]:
        targets: list[tuple[Subtask, SubSubtask | None, float]] = []
        for subtask in subtasks:
            subtask_weight = float(weight_by_subtask_id.get(subtask.id) or 0)
            active_children = [child for child in sorted(subtask.child_tasks, key=lambda item: (item.display_order, item.name)) if child.status == TaskStatus.ACTIVE]
            if active_children:
                child_weight = round(subtask_weight / len(active_children), 2)
                allocated = 0.0
                for index, child in enumerate(active_children):
                    weight = child_weight
                    if index == len(active_children) - 1:
                        weight = round(subtask_weight - allocated, 2)
                    allocated = round(allocated + weight, 2)
                    targets.append((subtask, child, weight))
            else:
                targets.append((subtask, None, subtask_weight))
        return targets

    def _assignment_targets_for_category(self, category: TaskCategory) -> list[tuple[Subtask, SubSubtask | None]]:
        targets: list[tuple[Subtask, SubSubtask | None]] = []
        for subtask in sorted(category.subtasks, key=lambda item: (item.display_order, item.name)):
            if subtask.status != TaskStatus.ACTIVE:
                continue
            active_children = [child for child in sorted(subtask.child_tasks, key=lambda item: (item.display_order, item.name)) if child.status == TaskStatus.ACTIVE]
            if active_children:
                targets.extend((subtask, child) for child in active_children)
            else:
                targets.append((subtask, None))
        return targets

    def _target_key(self, subtask_id: UUID, sub_subtask_id: UUID | None) -> tuple[UUID, UUID | None]:
        return subtask_id, sub_subtask_id

    def _ensure_default_other_subtask(self, category: TaskCategory, actor: User) -> None:
        existing_other = self.db.scalar(select(Subtask).where(
            Subtask.task_category_id == category.id,
            func.lower(func.trim(Subtask.name)) == 'other',
        ))
        if existing_other:
            return
        self.db.add(Subtask(
            task_category_id=category.id,
            name='Other',
            description='Default catch-all subtask',
            status=TaskStatus.ACTIVE,
            display_order=self._next_subtask_display_order(category.id),
            source_type=SubtaskSourceType.MANUAL,
            source_reference_id=None,
            source_configuration=None,
            count_method=None,
            completion_rule=None,
            supports_automatic_fetch=False,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        ))

    def _enum(self, enum_cls, value: str, error: str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error) from exc

    def _audit(self, action: str, actor: User, entity_type: str, entity_id: UUID, metadata: dict) -> None:
        AuditService(self.db).log(action=action, user_id=actor.id, entity_type=entity_type, entity_id=entity_id, category='TASK_MANAGEMENT', metadata=metadata)

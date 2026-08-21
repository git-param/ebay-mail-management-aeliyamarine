from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.session import get_db
from app.modules.task_management.models import SubSubtask, Subtask, TaskCategory, UserSubtaskAssignment
from app.modules.task_management.schemas import AssignmentPayload, AssignmentResponse, TaskAssignmentPayload, TaskCategoryPayload, TaskCategoryResponse, SubSubtaskPayload, SubSubtaskResponse, SubtaskPayload, SubtaskResponse, UserAssignmentSummary
from app.modules.task_management.service import TaskManagementService


router = APIRouter()


def serialize_subtask(subtask: Subtask) -> SubtaskResponse:
    return SubtaskResponse(
        id=subtask.id,
        task_category_id=subtask.task_category_id,
        name=subtask.name,
        description=subtask.description,
        status=subtask.status.value,
        source_type=subtask.source_type.value,
        source_reference_id=subtask.source_reference_id,
        source_configuration=subtask.source_configuration,
        count_method=subtask.count_method,
        completion_rule=subtask.completion_rule,
        supports_automatic_fetch=subtask.supports_automatic_fetch,
        assignment_count=len(subtask.assignments or []),
        child_tasks=[serialize_sub_subtask(child) for child in subtask.child_tasks],
        created_at=subtask.created_at,
        updated_at=subtask.updated_at,
    )


def serialize_sub_subtask(child: SubSubtask) -> SubSubtaskResponse:
    return SubSubtaskResponse(
        id=child.id,
        subtask_id=child.subtask_id,
        name=child.name,
        description=child.description,
        status=child.status.value,
        source_type=child.source_type.value,
        source_reference_id=child.source_reference_id,
        source_configuration=child.source_configuration,
        count_method=child.count_method,
        completion_rule=child.completion_rule,
        supports_automatic_fetch=child.supports_automatic_fetch,
        assignment_count=len(child.assignments or []),
        created_at=child.created_at,
        updated_at=child.updated_at,
    )


def serialize_category(category: TaskCategory) -> TaskCategoryResponse:
    return TaskCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        status=category.status.value,
        quality_weight=float(category.quality_weight or 0),
        subtasks=[serialize_subtask(subtask) for subtask in category.subtasks],
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def serialize_assignment(assignment: UserSubtaskAssignment) -> AssignmentResponse:
    subtask = assignment.subtask
    source_target = assignment.sub_subtask or subtask
    return AssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        subtask_id=assignment.subtask_id,
        sub_subtask_id=assignment.sub_subtask_id,
        quality_weight=float(assignment.quality_weight or 0),
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        auto_fetch_enabled=assignment.auto_fetch_enabled,
        status=assignment.status.value,
        subtask_name=subtask.name if subtask else None,
        sub_subtask_name=assignment.sub_subtask.name if assignment.sub_subtask else None,
        category_name=subtask.category.name if subtask and subtask.category else None,
        task_category_id=subtask.task_category_id if subtask else None,
        source_type=source_target.source_type.value if source_target else None,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.get('/categories', response_model=list[TaskCategoryResponse])
def list_categories(db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    return [serialize_category(category) for category in TaskManagementService(db).list_categories()]


@router.post('/categories', response_model=TaskCategoryResponse)
def create_category(payload: TaskCategoryPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_category(TaskManagementService(db).save_category(payload, current_user))


@router.patch('/categories/{category_id}', response_model=TaskCategoryResponse)
def update_category(category_id: UUID, payload: TaskCategoryPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_category(TaskManagementService(db).save_category(payload, current_user, category_id))


@router.delete('/categories/{category_id}')
def delete_category(category_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    TaskManagementService(db).delete_category(category_id, current_user)
    return {'message': 'Task category deleted.'}


@router.post('/subtasks', response_model=SubtaskResponse)
def create_subtask(payload: SubtaskPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_subtask(TaskManagementService(db).save_subtask(payload, current_user))


@router.patch('/subtasks/{subtask_id}', response_model=SubtaskResponse)
def update_subtask(subtask_id: UUID, payload: SubtaskPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_subtask(TaskManagementService(db).save_subtask(payload, current_user, subtask_id))


@router.delete('/subtasks/{subtask_id}')
def delete_subtask(subtask_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    TaskManagementService(db).delete_subtask(subtask_id, current_user)
    return {'message': 'Subtask deleted.'}


@router.post('/sub-subtasks', response_model=SubSubtaskResponse)
def create_sub_subtask(payload: SubSubtaskPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_sub_subtask(TaskManagementService(db).save_sub_subtask(payload, current_user))


@router.patch('/sub-subtasks/{sub_subtask_id}', response_model=SubSubtaskResponse)
def update_sub_subtask(sub_subtask_id: UUID, payload: SubSubtaskPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_sub_subtask(TaskManagementService(db).save_sub_subtask(payload, current_user, sub_subtask_id))


@router.delete('/sub-subtasks/{sub_subtask_id}')
def delete_sub_subtask(sub_subtask_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    TaskManagementService(db).delete_sub_subtask(sub_subtask_id, current_user)
    return {'message': 'Sub-subtask deleted.'}


@router.get('/assignments', response_model=UserAssignmentSummary)
def list_user_assignments(user_id: UUID, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    _ = current_user
    service = TaskManagementService(db)
    return UserAssignmentSummary(
        user_id=user_id,
        total_active_weight=service.active_weight_total(user_id),
        assignments=[serialize_assignment(item) for item in service.list_assignments(user_id)],
    )


@router.post('/assignments', response_model=AssignmentResponse)
def create_assignment(payload: AssignmentPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_assignment(TaskManagementService(db).save_assignment(payload, current_user))


@router.patch('/assignments/{assignment_id}', response_model=AssignmentResponse)
def update_assignment(assignment_id: UUID, payload: AssignmentPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    return serialize_assignment(TaskManagementService(db).save_assignment(payload, current_user, assignment_id))


@router.post('/task-assignments', response_model=UserAssignmentSummary)
def create_task_assignment(payload: TaskAssignmentPayload, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    """Assign every subtask under one task/category to a single agent in one action."""
    service = TaskManagementService(db)
    service.save_task_assignment(payload, current_user)
    return UserAssignmentSummary(
        user_id=payload.user_id,
        total_active_weight=service.active_weight_total(payload.user_id),
        assignments=[serialize_assignment(item) for item in service.list_assignments(payload.user_id)],
    )

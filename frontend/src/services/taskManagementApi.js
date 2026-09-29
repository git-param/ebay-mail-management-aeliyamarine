import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

function qs(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export const fetchTaskCategories = () => apiRequest(API.TASK_MANAGEMENT.CATEGORIES)
export const saveTaskCategory = (payload, id = '') => apiRequest(id ? apiPath(API.TASK_MANAGEMENT.CATEGORIES_BY_ID, { id }) : API.TASK_MANAGEMENT.CATEGORIES, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const deleteTaskCategory = (id) => apiRequest(apiPath(API.TASK_MANAGEMENT.CATEGORIES_BY_ID, { id }), {
  method: 'DELETE',
})
export const saveSubtask = (payload, id = '') => apiRequest(id ? apiPath(API.TASK_MANAGEMENT.SUBTASKS_BY_ID, { id }) : API.TASK_MANAGEMENT.SUBTASKS, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const deleteSubtask = (id) => apiRequest(apiPath(API.TASK_MANAGEMENT.SUBTASKS_BY_ID, { id }), {
  method: 'DELETE',
})
export const saveSubSubtask = (payload, id = '') => apiRequest(id ? apiPath(API.TASK_MANAGEMENT.SUB_SUBTASKS_BY_ID, { id }) : API.TASK_MANAGEMENT.SUB_SUBTASKS, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const deleteSubSubtask = (id) => apiRequest(apiPath(API.TASK_MANAGEMENT.SUB_SUBTASKS_BY_ID, { id }), {
  method: 'DELETE',
})
export const fetchUserTaskAssignments = (userId) => apiRequest(API.TASK_MANAGEMENT.ASSIGNMENTS + (qs({ user_id: userId })))
export const saveUserTaskAssignment = (payload, id = '') => apiRequest(id ? apiPath(API.TASK_MANAGEMENT.ASSIGNMENTS_BY_ID, { id }) : API.TASK_MANAGEMENT.ASSIGNMENTS, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const saveTaskAssignment = (payload) => apiRequest(API.TASK_MANAGEMENT.TASK_ASSIGNMENTS, {
  method: 'POST',
  body: JSON.stringify(payload),
})

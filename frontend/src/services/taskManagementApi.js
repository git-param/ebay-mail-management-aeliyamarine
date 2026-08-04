import { apiRequest } from './http'

function qs(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export const fetchTaskCategories = () => apiRequest('/task-management/categories')
export const saveTaskCategory = (payload, id = '') => apiRequest(`/task-management/categories${id ? `/${id}` : ''}`, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const saveSubtask = (payload, id = '') => apiRequest(`/task-management/subtasks${id ? `/${id}` : ''}`, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
export const fetchUserTaskAssignments = (userId) => apiRequest(`/task-management/assignments${qs({ user_id: userId })}`)
export const saveUserTaskAssignment = (payload, id = '') => apiRequest(`/task-management/assignments${id ? `/${id}` : ''}`, {
  method: id ? 'PATCH' : 'POST',
  body: JSON.stringify(payload),
})
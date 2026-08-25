import { apiRequest } from './http'

function getErrorMessage(status, data) {
  if (data.detail || data.message) {
    return data.detail || data.message
  }

  const messages = {
    400: 'The request is invalid. Please check the details and try again.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested user could not be found.',
    500: 'The server could not complete the request. Please try again later.',
  }

  return messages[status] || 'Something went wrong. Please try again.'
}

async function request(path, options = {}) {
  return apiRequest(path, options, getErrorMessage)
}

export function fetchUsers() {
  return request('/users')
}

export function fetchUser(userId) {
  return request(`/users/${userId}`)
}

export function createUser(payload) {
  return request('/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateUser(userId, payload) {
  return request(`/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteUser(userId) {
  return request(`/users/${userId}`, {
    method: 'DELETE',
  })
}

export function activateUser(userId) {
  return request(`/users/${userId}/activate`, {
    method: 'PATCH',
  })
}

export function deactivateUser(userId) {
  return request(`/users/${userId}/deactivate`, {
    method: 'PATCH',
  })
}

export function resetUserPassword(userId) {
  return request(`/users/${userId}/reset-password`, {
    method: 'POST',
  })
}

import { API, apiPath } from '../constants/api'
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
  return request(API.USERS.ROOT)
}

export function fetchUser(userId) {
  return request(apiPath(API.USERS.BY_USER_ID, { userId }))
}

export function createUser(payload) {
  return request(API.USERS.ROOT, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateUser(userId, payload) {
  return request(apiPath(API.USERS.BY_USER_ID, { userId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteUser(userId) {
  return request(apiPath(API.USERS.BY_USER_ID, { userId }), {
    method: 'DELETE',
  })
}

export function activateUser(userId) {
  return request(apiPath(API.USERS.BY_USER_ID_ACTIVATE, { userId }), {
    method: 'PATCH',
  })
}

export function deactivateUser(userId) {
  return request(apiPath(API.USERS.BY_USER_ID_DEACTIVATE, { userId }), {
    method: 'PATCH',
  })
}

export function resetUserPassword(userId) {
  return request(apiPath(API.USERS.BY_USER_ID_RESET_PASSWORD, { userId }), {
    method: 'POST',
  })
}

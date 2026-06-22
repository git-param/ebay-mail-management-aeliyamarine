import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || `Login request failed (${status})`)
}

export function loginUser(credentials) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function requestPasswordReset(payload) {
  return request('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function resetPassword(payload) {
  return request('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchCurrentSession() {
  return request('/auth/me')
}

export function logoutUser() {
  return request('/auth/logout', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

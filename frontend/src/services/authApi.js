import { API } from '../constants/api'
import { apiRequest } from './http'

async function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || `Login request failed (${status})`)
}

export function loginUser(credentials) {
  return request(API.AUTH.LOGIN, {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function requestPasswordReset(payload) {
  return request(API.AUTH.FORGOT_PASSWORD, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function resetPassword(payload) {
  return request(API.AUTH.RESET_PASSWORD, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchCurrentSession() {
  return request(API.AUTH.ME)
}

export function logoutUser() {
  return request(API.AUTH.LOGOUT, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

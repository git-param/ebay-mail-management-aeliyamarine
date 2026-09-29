import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

function validationMessage(detail) {
  if (!Array.isArray(detail)) return ''

  return detail
    .map((item) => {
      const field = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== 'body').join('.')
        : ''
      return field ? `${field}: ${item.msg}` : item.msg
    })
    .filter(Boolean)
    .join('; ')
}

function getLeaveErrorMessage(status, data) {
  if (Array.isArray(data.detail)) {
    return validationMessage(data.detail) || `Request failed (${status})`
  }

  return data.detail || data.message || `Request failed (${status})`
}

function qs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export function fetchLeavePolicy() {
  return apiRequest(API.LEAVE_MANAGEMENT.POLICY, {}, getLeaveErrorMessage)
}

export function updateLeavePolicy(payload) {
  return apiRequest(API.LEAVE_MANAGEMENT.POLICY, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function createLeaveRequest(payload) {
  return apiRequest(API.LEAVE_MANAGEMENT.REQUESTS, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function fetchLeaveRequests(params) {
  return apiRequest(API.LEAVE_MANAGEMENT.REQUESTS + (qs(params)), {}, getLeaveErrorMessage)
}

export function reviewLeaveRequest(requestId, payload) {
  return apiRequest(apiPath(API.LEAVE_MANAGEMENT.REQUESTS_BY_REQUEST_ID_REVIEW, { requestId }), {
    method: 'POST',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function cancelLeaveRequest(requestId) {
  return apiRequest(apiPath(API.LEAVE_MANAGEMENT.REQUESTS_BY_REQUEST_ID_CANCEL, { requestId }), {
    method: 'POST',
    body: JSON.stringify({}),
  }, getLeaveErrorMessage)
}

export function fetchLeaveBalances(params) {
  return apiRequest(API.LEAVE_MANAGEMENT.BALANCES + (qs(params)), {}, getLeaveErrorMessage)
}

export function fetchLeaveAdminSummary(params) {
  return apiRequest(API.LEAVE_MANAGEMENT.ADMIN_SUMMARY + (qs(params)), {}, getLeaveErrorMessage)
}

export function updateLeaveAdminSummary(payload) {
  return apiRequest(API.LEAVE_MANAGEMENT.ADMIN_SUMMARY, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function fetchLeaveCarryForward(params) {
  return apiRequest(API.LEAVE_MANAGEMENT.CARRY_FORWARD + (qs(params)), {}, getLeaveErrorMessage)
}

export function updateLeaveCarryForward(payload) {
  return apiRequest(API.LEAVE_MANAGEMENT.CARRY_FORWARD, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function fetchMyLeaveBalance(params) {
  return apiRequest(API.LEAVE_MANAGEMENT.BALANCES_ME + (qs(params)), {}, getLeaveErrorMessage)
}

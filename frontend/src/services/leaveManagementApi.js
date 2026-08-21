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
  return apiRequest('/leave-management/policy', {}, getLeaveErrorMessage)
}

export function updateLeavePolicy(payload) {
  return apiRequest('/leave-management/policy', {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function createLeaveRequest(payload) {
  return apiRequest('/leave-management/requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function fetchLeaveRequests(params) {
  return apiRequest(`/leave-management/requests${qs(params)}`, {}, getLeaveErrorMessage)
}

export function reviewLeaveRequest(requestId, payload) {
  return apiRequest(`/leave-management/requests/${requestId}/review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function cancelLeaveRequest(requestId) {
  return apiRequest(`/leave-management/requests/${requestId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({}),
  }, getLeaveErrorMessage)
}

export function fetchLeaveBalances(params) {
  return apiRequest(`/leave-management/balances${qs(params)}`, {}, getLeaveErrorMessage)
}

export function fetchLeaveAdminSummary(params) {
  return apiRequest(`/leave-management/admin-summary${qs(params)}`, {}, getLeaveErrorMessage)
}

export function updateLeaveAdminSummary(payload) {
  return apiRequest('/leave-management/admin-summary', {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, getLeaveErrorMessage)
}

export function fetchMyLeaveBalance(params) {
  return apiRequest(`/leave-management/balances/me${qs(params)}`, {}, getLeaveErrorMessage)
}

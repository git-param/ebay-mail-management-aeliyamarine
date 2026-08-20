import { apiRequest } from './http'

function qs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export function fetchLeavePolicy() {
  return apiRequest('/leave-management/policy')
}

export function updateLeavePolicy(payload) {
  return apiRequest('/leave-management/policy', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function createLeaveRequest(payload) {
  return apiRequest('/leave-management/requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchLeaveRequests(params) {
  return apiRequest(`/leave-management/requests${qs(params)}`)
}

export function reviewLeaveRequest(requestId, payload) {
  return apiRequest(`/leave-management/requests/${requestId}/review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function cancelLeaveRequest(requestId) {
  return apiRequest(`/leave-management/requests/${requestId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function fetchLeaveBalances(params) {
  return apiRequest(`/leave-management/balances${qs(params)}`)
}

export function fetchMyLeaveBalance(params) {
  return apiRequest(`/leave-management/balances/me${qs(params)}`)
}

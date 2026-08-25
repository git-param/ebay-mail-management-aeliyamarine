import { apiFetch, apiRequest } from './http'

function qs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

// ---- Configuration ----

export function fetchPmsConfig() {
  return apiRequest('/pms/config')
}

export function createPmsConfig(payload) {
  return apiRequest('/pms/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePmsConfig(configId, payload) {
  return apiRequest(`/pms/config/${configId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deletePmsConfig(configId) {
  return apiRequest(`/pms/config/${configId}`, {
    method: 'DELETE',
  })
}

// ---- Monthly PMS ----

export function fetchPmsMonthlyTable(params) {
  return apiRequest(`/pms/monthly${qs(params)}`)
}

export async function exportPmsMonthlyTable(params) {
  const response = await apiFetch(`/pms/monthly/export${qs(params)}`)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || data.message || 'Unable to export PMS data.')
  }
  return response.blob()
}

export function fetchPmsMonthlyRecord(userId, params) {
  return apiRequest(`/pms/monthly/${userId}${qs(params)}`)
}

export function refreshPmsAutoValues(payload) {
  return apiRequest('/pms/monthly/refresh', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function savePmsMonthly(payload) {
  return apiRequest('/pms/monthly', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ---- History ----

export function fetchPmsHistory(params) {
  return apiRequest(`/pms/history${qs(params)}`)
}

// ---- Employee of the Month ----

export function fetchPmsEmployeeOfMonth(params) {
  return apiRequest(`/pms/employee-of-month${qs(params)}`)
}

export function fetchPmsEmployeeOfMonthStats() {
  return apiRequest('/pms/employee-of-month/stats')
}

export function resolvePmsEmployeeOfMonth(payload) {
  return apiRequest('/pms/employee-of-month/resolve', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

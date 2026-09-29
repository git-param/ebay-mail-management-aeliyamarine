import { API, apiPath } from '../constants/api'
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
  return apiRequest(API.PMS.CONFIG)
}

export function createPmsConfig(payload) {
  return apiRequest(API.PMS.CONFIG, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePmsConfig(configId, payload) {
  return apiRequest(apiPath(API.PMS.CONFIG_BY_CONFIG_ID, { configId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deletePmsConfig(configId) {
  return apiRequest(apiPath(API.PMS.CONFIG_BY_CONFIG_ID, { configId }), {
    method: 'DELETE',
  })
}

// ---- Monthly PMS ----

export function fetchPmsMonthlyTable(params) {
  return apiRequest(API.PMS.MONTHLY + (qs(params)))
}

export function fetchPmsTargetAchievement(params) {
  return apiRequest(API.PMS.MONTHLY_TARGET_ACHIEVEMENT + (qs(params)))
}

export function updatePmsTargetAchievement(payload) {
  return apiRequest(API.PMS.MONTHLY_TARGET_ACHIEVEMENT, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function fetchPmsAvailablePeriods(params) {
  return apiRequest(API.PMS.MONTHLY_AVAILABLE_PERIODS + (qs(params)))
}

export async function exportPmsMonthlyTable(params) {
  const response = await apiFetch(API.PMS.MONTHLY_EXPORT + (qs(params)))
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || data.message || 'Unable to export PMS data.')
  }
  return response.blob()
}

export function fetchPmsMonthlyRecord(userId, params) {
  return apiRequest(apiPath(API.PMS.MONTHLY_BY_USER_ID, { userId }) + (qs(params)))
}

export function refreshPmsAutoValues(payload) {
  return apiRequest(API.PMS.MONTHLY_REFRESH, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function savePmsMonthly(payload) {
  return apiRequest(API.PMS.MONTHLY, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ---- History ----

export function fetchPmsHistory(params) {
  return apiRequest(API.PMS.HISTORY + (qs(params)))
}

// ---- Employee of the Month ----

export function fetchPmsEmployeeOfMonth(params) {
  return apiRequest(API.PMS.EMPLOYEE_OF_MONTH + (qs(params)))
}

export function fetchPmsEmployeeOfMonthStats() {
  return apiRequest(API.PMS.EMPLOYEE_OF_MONTH_STATS)
}

export function resolvePmsEmployeeOfMonth(payload) {
  return apiRequest(API.PMS.EMPLOYEE_OF_MONTH_RESOLVE, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

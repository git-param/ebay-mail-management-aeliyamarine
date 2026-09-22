import { apiFetch, apiRequest } from './http'

function getErrorMessage(status, data) {
  if (data.detail || data.message) {
    return data.detail || data.message
  }

  const messages = {
    400: 'Choose a reason before starting your break.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have permission to view this break data.',
    404: 'No active break was found.',
    409: 'You are already on a break.',
  }

  return messages[status] || 'Unable to update break management right now.'
}

async function request(path, options = {}) {
  return apiRequest(path, options, getErrorMessage)
}

function withQuery(path, params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value)
    }
  })
  const value = query.toString()
  return value ? `${path}?${value}` : path
}

export function fetchBreakStatus() {
  return request('/break-management/status')
}

export function startBreak(reason) {
  return request('/break-management/start', {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function endBreak() {
  return request('/break-management/end', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function fetchBreakHistory(params = {}) {
  return request(withQuery('/break-management/history', params))
}

export function fetchBreakOverview(params = {}) {
  return request(withQuery('/break-management/overview', params))
}

export function fetchBreakEmployees() {
  return request('/break-management/employees')
}

export async function exportBreakReport({ date_from, date_to, user_ids }) {
  const query = new URLSearchParams({ date_from, date_to })
  user_ids?.forEach((id) => query.append('user_ids', id))
  const response = await apiFetch(`/break-management/export?${query}`)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || 'Unable to export break report.')
  }
  return response.blob()
}

import { apiFetch } from './http'

function buildQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value)
    }
  })
  const queryString = query.toString()
  return queryString ? `?${queryString}` : ''
}

export async function fetchAuditLogs(params) {
  const response = await apiFetch(`/audit-logs${buildQuery(params)}`)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load audit logs')
  }
  return data
}

export async function exportAuditLogs() {
  const response = await apiFetch('/audit-logs/export')
  if (!response.ok) {
    throw new Error('Unable to export audit logs')
  }
  return response.blob()
}

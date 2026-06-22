const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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
  const response = await fetch(`${API_BASE_URL}/audit-logs${buildQuery(params)}`, {
    credentials: 'include',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load audit logs')
  }
  return data
}

export async function exportAuditLogs() {
  const response = await fetch(`${API_BASE_URL}/audit-logs/export`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error('Unable to export audit logs')
  }
  return response.blob()
}

import { API } from '../constants/api'
import { apiFetch, apiRequest } from './http'

export const previewAuditDeletion = (dates) => apiRequest(API.AUDIT_LOGS.DELETION_PREVIEW + (buildQuery(dates)))
export const deleteAuditLogs = (payload) => apiRequest(API.AUDIT_LOGS.ROOT, { method: 'DELETE', body: JSON.stringify(payload) })

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
  const response = await apiFetch(API.AUDIT_LOGS.ROOT + (buildQuery(params)))
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load audit logs')
  }
  return data
}

export async function fetchAuditFilterOptions() {
  const response = await apiFetch(API.AUDIT_LOGS.FILTERS)
  if (!response.ok) throw new Error('Unable to load audit filters')
  return response.json()
}

export async function exportAuditLogs(params = {}) {
  const response = await apiFetch(API.AUDIT_LOGS.EXPORT + (buildQuery(params)))
  if (!response.ok) {
    throw new Error('Unable to export audit logs')
  }
  return response.blob()
}

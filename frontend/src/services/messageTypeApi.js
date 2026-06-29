import { apiFetch, apiRequest } from './http'

function query(params = {}) {
  const value = new URLSearchParams(Object.entries(params).filter(([, item]) => item !== '' && item != null)).toString()
  return value ? `?${value}` : ''
}
export const fetchMessageTypeTree = () => apiRequest('/message-types/tree')
export const fetchMessageTypes = (includeDeleted = false) => apiRequest(`/message-types${includeDeleted ? '?include_deleted=true' : ''}`)
export const createMessageType = (payload) => apiRequest('/message-types', { method: 'POST', body: JSON.stringify(payload) })
export const updateMessageType = (id, payload) => apiRequest(`/message-types/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteMessageType = (id) => apiRequest(`/message-types/${id}`, { method: 'DELETE' })
export const setMessageTypeStatus = (id, payload) => apiRequest(`/message-types/${id}/status`, { method: 'PATCH', body: JSON.stringify(payload) })
export const fetchMessageReport = (params) => apiRequest(`/reports/message-types${query(params)}`)
export async function exportMessageReport(params) {
  const response = await apiFetch(`/reports/message-types/export${query(params)}`)
  if (!response.ok) throw new Error('Unable to export message report')
  return response.blob()
}

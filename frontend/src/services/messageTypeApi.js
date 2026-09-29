import { API, apiPath } from '../constants/api'
import { apiFetch, apiRequest } from './http'

function query(params = {}) {
  const value = new URLSearchParams(Object.entries(params).filter(([, item]) => item !== '' && item != null)).toString()
  return value ? `?${value}` : ''
}
export const fetchMessageTypeTree = () => apiRequest(API.MESSAGE_TYPES.TREE)
export const fetchMessageTypes = (includeDeleted = false) => apiRequest(API.MESSAGE_TYPES.ROOT + (includeDeleted ? '?include_deleted=true' : ''))
export const createMessageType = (payload) => apiRequest(API.MESSAGE_TYPES.ROOT, { method: 'POST', body: JSON.stringify(payload) })
export const updateMessageType = (id, payload) => apiRequest(apiPath(API.MESSAGE_TYPES.BY_ID, { id }), { method: 'PUT', body: JSON.stringify(payload) })
export const deleteMessageType = (id) => apiRequest(apiPath(API.MESSAGE_TYPES.BY_ID, { id }), { method: 'DELETE' })
export const setMessageTypeStatus = (id, payload) => apiRequest(apiPath(API.MESSAGE_TYPES.BY_ID_STATUS, { id }), { method: 'PATCH', body: JSON.stringify(payload) })
export const fetchMessageReport = (params) => apiRequest(API.REPORTS.MESSAGE_TYPES + (query(params)))
export async function exportMessageReport(params) {
  const response = await apiFetch(API.REPORTS.MESSAGE_TYPES_EXPORT + (query(params)))
  if (!response.ok) throw new Error('Unable to export message report')
  return response.blob()
}

import { apiRequest } from './http'

function qs(params) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) {
      if (value.length) search.set(key, value.join(','))
      return
    }
    search.set(key, value)
  })
  return search.toString()
}

export function fetchSoldPostingOrders(params) {
  const query = qs(params)
  return apiRequest(`/sold-posting/orders${query ? `?${query}` : ''}`)
}

export function fetchSoldPostingDetail(orderId) {
  return apiRequest(`/sold-posting/orders/${encodeURIComponent(orderId)}`)
}

export function fetchSoldPostingOptions() {
  return apiRequest('/sold-posting/filter-options')
}

export function syncSoldPosting() {
  return apiRequest('/sold-posting/sync', { method: 'POST', body: JSON.stringify({}) })
}

export function updateSoldPostingLineItem(lineItemRecordId, payload) {
  return apiRequest(`/sold-posting/line-items/${encodeURIComponent(lineItemRecordId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function markSoldPostingCopied(lineItemRecordId) {
  return apiRequest(`/sold-posting/line-items/${encodeURIComponent(lineItemRecordId)}/copied`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

import { API, apiPath } from '../constants/api'
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
  return apiRequest(API.SOLD_POSTING.ORDERS + (query ? `?${query}` : ''))
}

export function fetchSoldPostingDetail(orderId) {
  return apiRequest(apiPath(API.SOLD_POSTING.ORDERS_BY_ORDER_ID, { orderId: encodeURIComponent(orderId) }))
}

export function fetchOrderBuyerConversation(orderId, accountId) {
  const path = apiPath(API.SOLD_POSTING.ORDER_CONVERSATION, {
    orderId: encodeURIComponent(orderId),
  })
  return apiRequest(`${path}?${qs({ account_id: accountId })}`, { method: 'POST' })
}

export function fetchSoldPostingOptions() {
  return apiRequest(API.SOLD_POSTING.FILTER_OPTIONS)
}

export function syncSoldPosting() {
  return apiRequest(API.SOLD_POSTING.SYNC, { method: 'POST', body: JSON.stringify({}) })
}

export function updateSoldPostingLineItem(lineItemRecordId, payload) {
  return apiRequest(apiPath(API.SOLD_POSTING.LINE_ITEMS_BY_LINE_ITEM_RECORD_ID, { lineItemRecordId: encodeURIComponent(lineItemRecordId) }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function markSoldPostingCopied(lineItemRecordId) {
  return apiRequest(apiPath(API.SOLD_POSTING.LINE_ITEMS_BY_LINE_ITEM_RECORD_ID_COPIED, { lineItemRecordId: encodeURIComponent(lineItemRecordId) }), {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

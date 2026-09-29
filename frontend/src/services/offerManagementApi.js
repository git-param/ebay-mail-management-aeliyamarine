import { API, apiPath } from '../constants/api'
import { apiFetch, apiFormRequest, apiRequest } from './http'

function query(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => {
    if (typeof data.detail === 'string') return data.detail
    if (data.detail?.message) return data.detail.message
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg).filter(Boolean).join(' ') || `Offer Management request failed (${status})`
    }
    return data.message || `Offer Management request failed (${status})`
  })
}

export function fetchOfferEntries(params) {
  return request(API.OFFER_MANAGEMENT.ROOT + (query(params)))
}

export function fetchOfferSummary(params) {
  return request(API.OFFER_MANAGEMENT.SUMMARY + (query(params)))
}

export function fetchOfferLookups() {
  return request(API.OFFER_MANAGEMENT.LOOKUPS)
}

export function lookupOfferListing(listing) {
  return request(API.OFFER_MANAGEMENT.LOOKUP + (query({ listing })))
}

export function checkOfferListingDuplicate(listing) {
  return request(API.OFFER_MANAGEMENT.DUPLICATE_CHECK + (query({ listing })))
}

export function createOfferEntry(payload) {
  return request(API.OFFER_MANAGEMENT.ROOT, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateOfferEntry(id, payload) {
  return request(apiPath(API.OFFER_MANAGEMENT.BY_ID, { id }), { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteOfferEntry(id) {
  return request(apiPath(API.OFFER_MANAGEMENT.BY_ID, { id }), { method: 'DELETE' })
}

export function bulkDeleteOfferEntries(entryIds) {
  return request(API.OFFER_MANAGEMENT.BULK_DELETE, {
    method: 'POST',
    body: JSON.stringify({ entry_ids: entryIds }),
  })
}

export function importOfferEntriesExcel(file) {
  const formData = new FormData()
  formData.append('file', file)
  return apiFormRequest(API.OFFER_MANAGEMENT.IMPORT_EXCEL, formData, (status, data) => data.detail || data.message || `Offer import failed (${status})`)
}

export function fetchOfferEntry(id) {
  return request(apiPath(API.OFFER_MANAGEMENT.BY_ID, { id }))
}

export function fetchOfferHistory(id) {
  return request(apiPath(API.OFFER_MANAGEMENT.BY_ID_HISTORY, { id }))
}

export async function exportOfferEntries(params) {
  const response = await apiFetch(API.OFFER_MANAGEMENT.EXPORT + (query(params)))
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || 'Unable to export offer entries.')
  }
  return response.blob()
}

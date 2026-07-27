import { apiFetch, apiRequest } from './http'

function query(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

function request(path, options = {}) {
  return apiRequest(path, options, (status, data) => data.detail || data.message || `Offer Management request failed (${status})`)
}

export function fetchOfferEntries(params) {
  return request(`/offer-management${query(params)}`)
}

export function fetchOfferSummary(params) {
  return request(`/offer-management/summary${query(params)}`)
}

export function fetchOfferLookups() {
  return request('/offer-management/lookups')
}

export function lookupOfferListing(listing) {
  return request(`/offer-management/lookup${query({ listing })}`)
}

export function createOfferEntry(payload) {
  return request('/offer-management', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateOfferEntry(id, payload) {
  return request(`/offer-management/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function fetchOfferEntry(id) {
  return request(`/offer-management/${id}`)
}

export function fetchOfferHistory(id) {
  return request(`/offer-management/${id}/history`)
}

export async function exportOfferEntries(params) {
  const response = await apiFetch(`/offer-management/export${query(params)}`)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || 'Unable to export offer entries.')
  }
  return response.blob()
}

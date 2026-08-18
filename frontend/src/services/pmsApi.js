import { apiRequest } from './http'

function qs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export function fetchPmsDraft(params) {
  return apiRequest(`/pms/draft${qs(params)}`)
}

export function fetchPmsEntries(params) {
  return apiRequest(`/pms/entries${qs(params)}`)
}

export function savePmsEntry(payload) {
  return apiRequest('/pms/entries', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loadPmsDailyEntries(params) {
  return apiRequest(`/pms/daily-entries/load${qs(params)}`)
}

export function uploadPmsDailyEntries(entries) {
  return apiRequest('/pms/daily-entries/upload', {
    method: 'POST',
    body: JSON.stringify({ entries }),
  })
}

export function fetchPmsSlaReview(params) {
  return apiRequest(`/pms/sla-review${qs(params)}`)
}
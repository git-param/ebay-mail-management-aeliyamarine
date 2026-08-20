import { apiRequest } from './http'

function qs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export function fetchDailyEntryDraft(params) {
  return apiRequest(`/dailyEntry/draft${qs(params)}`)
}

export function fetchDailyEntries(params) {
  return apiRequest(`/dailyEntry/entries${qs(params)}`)
}

export function saveDailyEntry(payload) {
  return apiRequest('/dailyEntry/entries', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loadDailyEntries(params) {
  return apiRequest(`/dailyEntry/daily-entries/load${qs(params)}`)
}

export function uploadDailyEntries(entries) {
  return apiRequest('/dailyEntry/daily-entries/upload', {
    method: 'POST',
    body: JSON.stringify({ entries }),
  })
}

export function fetchDailyEntrySlaReview(params) {
  return apiRequest(`/dailyEntry/sla-review${qs(params)}`)
}
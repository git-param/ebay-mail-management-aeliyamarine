import { API } from '../constants/api'
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
  return apiRequest(API.DAILY_ENTRY.DRAFT + (qs(params)))
}

export function fetchDailyEntries(params) {
  return apiRequest(API.DAILY_ENTRY.ENTRIES + (qs(params)))
}

export function saveDailyEntry(payload) {
  return apiRequest(API.DAILY_ENTRY.ENTRIES, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loadDailyEntries(params) {
  return apiRequest(API.DAILY_ENTRY.DAILY_ENTRIES_LOAD + (qs(params)))
}

export function uploadDailyEntries(entries) {
  return apiRequest(API.DAILY_ENTRY.DAILY_ENTRIES_UPLOAD, {
    method: 'POST',
    body: JSON.stringify({ entries }),
  })
}

export function deleteDailyEntries(payload) {
  return apiRequest(API.DAILY_ENTRY.DAILY_ENTRIES_DELETE, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchDailyEntrySlaReview(params) {
  return apiRequest(API.DAILY_ENTRY.SLA_REVIEW + (qs(params)))
}

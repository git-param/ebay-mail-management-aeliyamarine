import { apiRequest } from './http'

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

export function searchAcrossPlatforms(query, limit = 10, signal) {
  return apiRequest(
    `/search-sku${buildQuery({ q: query, limit })}`,
    { signal },
    (status, data) => data.detail || data.message || `Cross-platform search failed (${status}).`,
  )
}

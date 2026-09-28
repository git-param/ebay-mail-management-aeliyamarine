import { apiRequest } from './http'

const base = '/integrations/ebay/best-offers'
export const fetchCurrentOffers = (filters = {}) => {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value != null))
  return apiRequest(`${base}/current?${query}`)
}
export const fetchBestOfferAccounts = () => apiRequest(`${base}/accounts`)
export const fetchBestOfferConfig = () => apiRequest(`${base}/config`)
export const updateBestOfferConfig = (payload) => apiRequest(`${base}/config`, { method: 'PATCH', body: JSON.stringify(payload) })
export const syncBestOffers = (accountIds, includeHistory = false) => apiRequest(`${base}/sync`, { method: 'POST', body: JSON.stringify({ account_ids: accountIds, include_history: includeHistory }) })
export const fetchBestOfferJob = (id) => apiRequest(`${base}/jobs/${id}`)
export const cancelBestOfferJob = (id) => apiRequest(`${base}/jobs/${id}/cancel`, { method: 'POST' })
export const respondToBestOffer = (id, payload) => apiRequest(`${base}/${id}/respond`, { method: 'POST', body: JSON.stringify(payload) })

export const authorizeOfferActivity = (id) => apiRequest(`${base}/activity/${id}/authorize`, { method: 'POST' })
export const setupOfferActivity = (id) => apiRequest(`${base}/activity/${id}/setup`, { method: 'POST' })

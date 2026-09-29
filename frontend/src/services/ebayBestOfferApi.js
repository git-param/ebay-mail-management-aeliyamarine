import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'


export const fetchCurrentOffers = (filters = {}) => {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value != null))
  return apiRequest(API.EBAY_BEST_OFFERS.CURRENT + '?' + (query))
}
export const fetchBestOfferAccounts = () => apiRequest(API.EBAY_BEST_OFFERS.ACCOUNTS)
export const fetchBestOfferConfig = () => apiRequest(API.EBAY_BEST_OFFERS.CONFIG)
export const updateBestOfferConfig = (payload) => apiRequest(API.EBAY_BEST_OFFERS.CONFIG, { method: 'PATCH', body: JSON.stringify(payload) })
export const syncBestOffers = (accountIds, includeHistory = false) => apiRequest(API.EBAY_BEST_OFFERS.SYNC, { method: 'POST', body: JSON.stringify({ account_ids: accountIds, include_history: includeHistory }) })
export const fetchBestOfferJob = (id) => apiRequest(apiPath(API.EBAY_BEST_OFFERS.JOBS_BY_ID, { id }))
export const cancelBestOfferJob = (id) => apiRequest(apiPath(API.EBAY_BEST_OFFERS.JOBS_BY_ID_CANCEL, { id }), { method: 'POST' })
export const respondToBestOffer = (id, payload) => apiRequest(apiPath(API.EBAY_BEST_OFFERS.BY_ID_RESPOND, { id }), { method: 'POST', body: JSON.stringify(payload) })

export const authorizeOfferActivity = (id) => apiRequest(apiPath(API.EBAY_BEST_OFFERS.ACTIVITY_BY_ID_AUTHORIZE, { id }), { method: 'POST' })
export const setupOfferActivity = (id) => apiRequest(apiPath(API.EBAY_BEST_OFFERS.ACTIVITY_BY_ID_SETUP, { id }), { method: 'POST' })

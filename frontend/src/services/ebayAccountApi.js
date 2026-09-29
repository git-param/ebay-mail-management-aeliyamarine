import { API, apiPath } from '../constants/api'
import { apiRequest } from './http'

function getErrorMessage(status, data) {
  if (data.detail || data.message) {
    return data.detail || data.message
  }

  const messages = {
    400: 'The account details are invalid. Please check and try again.',
    401: 'Your session has expired. Please sign in again.',
    403: 'You do not have permission to manage eBay accounts.',
    404: 'The requested eBay account could not be found.',
    500: 'The server could not complete the request. Please try again later.',
  }

  return messages[status] || 'Something went wrong. Please try again.'
}

async function request(path, options = {}) {
  return apiRequest(path, options, getErrorMessage)
}

export function fetchEbayAccounts() {
  return request(API.EBAY_ACCOUNTS.ROOT)
}

export function fetchEbayAccount(accountId) {
  return request(apiPath(API.EBAY_ACCOUNTS.BY_ACCOUNT_ID, { accountId }))
}

export function createEbayAccount(payload) {
  return request(API.EBAY_ACCOUNTS.ROOT, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchEbaySyncStatus(syncLogId) {
  return request(apiPath(API.EBAY_INTEGRATION.SYNC_STATUS_BY_SYNC_LOG_ID, { syncLogId }))
}

export function updateEbayAccount(accountId, payload) {
  return request(apiPath(API.EBAY_ACCOUNTS.BY_ACCOUNT_ID, { accountId }), {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function activateEbayAccount(accountId) {
  return request(apiPath(API.EBAY_ACCOUNTS.BY_ACCOUNT_ID_ACTIVATE, { accountId }), {
    method: 'PATCH',
  })
}

export function deactivateEbayAccount(accountId) {
  return request(apiPath(API.EBAY_ACCOUNTS.BY_ACCOUNT_ID_DEACTIVATE, { accountId }), {
    method: 'PATCH',
  })
}

export function deleteEbayAccount(accountId) {
  return request(apiPath(API.EBAY_ACCOUNTS.BY_ACCOUNT_ID, { accountId }), {
    method: 'DELETE',
  })
}

export function connectEbayAccount(accountId) {
  return request(API.EBAY_INTEGRATION.CONNECT, {
    method: 'POST',
    body: JSON.stringify({ account_id: accountId }),
  })
}

export function submitManualEbayCallback(payload) {
  return request(API.EBAY_INTEGRATION.MANUAL_CALLBACK, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchEbayApiUsage() {
  return request(API.EBAY_INTEGRATION.API_USAGE)
}

export function fetchEbayAutoSyncStatus() {
  return request(API.EBAY_INTEGRATION.AUTO_SYNC)
}

export function updateEbayAutoSyncStatus(enabled, intervalMinutes) {
  return request(API.EBAY_INTEGRATION.AUTO_SYNC, {
    method: 'PATCH',
    body: JSON.stringify({ enabled, interval_minutes: intervalMinutes }),
  })
}

export function syncEbayAccount(accountId) {
  return request(apiPath(API.EBAY_INTEGRATION.SYNC_BY_ACCOUNT_ID, { accountId }), {
    method: 'POST',
  })
}

export function syncAllEbayAccounts() {
  return request(API.EBAY_INTEGRATION.SYNC_ALL, {
    method: 'POST',
  })
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

function getAuthToken() {
  return localStorage.getItem('accessToken') || ''
}

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
  const token = getAuthToken()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const error = new Error(getErrorMessage(response.status, data))
    error.status = response.status
    throw error
  }

  return data
}

export function fetchEbayAccounts() {
  return request('/ebay-accounts')
}

export function fetchEbayAccount(accountId) {
  return request(`/ebay-accounts/${accountId}`)
}

export function createEbayAccount(payload) {
  return request('/ebay-accounts', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateEbayAccount(accountId, payload) {
  return request(`/ebay-accounts/${accountId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function activateEbayAccount(accountId) {
  return request(`/ebay-accounts/${accountId}/activate`, {
    method: 'PATCH',
  })
}

export function deactivateEbayAccount(accountId) {
  return request(`/ebay-accounts/${accountId}/deactivate`, {
    method: 'PATCH',
  })
}

export function deleteEbayAccount(accountId) {
  return request(`/ebay-accounts/${accountId}`, {
    method: 'DELETE',
  })
}

export function connectEbayAccount(accountId) {
  return request('/integrations/ebay/connect', {
    method: 'POST',
    body: JSON.stringify({ account_id: accountId }),
  })
}

export function submitManualEbayCallback(payload) {
  return request('/integrations/ebay/manual-callback', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchEbayApiUsage() {
  return request('/integrations/ebay/api-usage')
}

export function syncEbayAccount(accountId) {
  return request(`/integrations/ebay/sync/${accountId}`, {
    method: 'POST',
  })
}

export function syncAllEbayAccounts() {
  return request('/integrations/ebay/sync-all', {
    method: 'POST',
  })
}

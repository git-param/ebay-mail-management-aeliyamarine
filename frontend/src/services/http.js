const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

let refreshPromise = null

export function clearStoredSession() {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')
  localStorage.removeItem('currentUser')
}

export function storeSessionUser(user) {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')
  localStorage.setItem('currentUser', JSON.stringify(user))
}

function buildHeaders(options = {}) {
  const headers = {
    ...options.headers,
  }

  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  return headers
}

async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    }).finally(() => {
      refreshPromise = null
    })
  }

  const response = await refreshPromise
  if (!response.ok) {
    clearStoredSession()
    return false
  }

  const data = await response.json().catch(() => ({}))
  if (data.user) {
    storeSessionUser(data.user)
  }
  return true
}

export async function apiFetch(path, options = {}) {
  const shouldAttemptRefresh = options.authRetry !== false && !path.startsWith('/auth/refresh') && !path.startsWith('/auth/login')
  const requestOptions = {
    credentials: 'include',
    ...options,
    headers: buildHeaders(options),
  }

  delete requestOptions.authRetry

  let response = await fetch(`${API_BASE_URL}${path}`, requestOptions)

  if (response.status === 401 && shouldAttemptRefresh) {
    const refreshed = await refreshSession()
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${path}`, requestOptions)
    }
  }

  return response
}

export async function apiRequest(path, options = {}, getErrorMessage) {
  const response = await apiFetch(path, options)

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const fallback = getErrorMessage
      ? getErrorMessage(response.status, data)
      : data.detail || data.message || `Request failed (${response.status})`
    const error = new Error(fallback)
    error.status = response.status
    throw error
  }

  return data
}

export async function apiFormRequest(path, formData, getErrorMessage) {
  const response = await apiFetch(path, {
    method: 'POST',
    body: formData,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const fallback = getErrorMessage
      ? getErrorMessage(response.status, data)
      : data.detail || data.message || `Request failed (${response.status})`
    const error = new Error(fallback)
    error.status = response.status
    throw error
  }

  return data
}

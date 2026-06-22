const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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

export async function apiRequest(path, options = {}, getErrorMessage) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const fallback = getErrorMessage
      ? getErrorMessage(response.status, data)
      : data.detail || data.message || `Request failed (${response.status})`
    throw new Error(fallback)
  }

  return data
}

export async function apiFormRequest(path, formData, getErrorMessage) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    const fallback = getErrorMessage
      ? getErrorMessage(response.status, data)
      : data.detail || data.message || `Request failed (${response.status})`
    throw new Error(fallback)
  }

  return data
}

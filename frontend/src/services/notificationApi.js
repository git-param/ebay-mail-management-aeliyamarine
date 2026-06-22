const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function request(path, options = {}) {
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
    throw new Error(data.detail || data.message || 'Something went wrong')
  }
  return data
}

export function fetchNotifications() {
  return request('/notifications?limit=10')
}

export function markNotificationsRead() {
  return request('/notifications/read', { method: 'PATCH' })
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

function getAuthToken() {
  return localStorage.getItem('accessToken') || ''
}

export async function fetchAnalyticsDashboard() {
  const token = getAuthToken()
  const response = await fetch(`${API_BASE_URL}/analytics/dashboard`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load analytics')
  }
  return data
}

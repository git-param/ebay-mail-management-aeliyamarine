const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export async function fetchAnalyticsDashboard() {
  const response = await fetch(`${API_BASE_URL}/analytics/dashboard`, {
    credentials: 'include',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load analytics')
  }
  return data
}

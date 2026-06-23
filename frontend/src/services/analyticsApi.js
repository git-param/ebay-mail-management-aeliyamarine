const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/**
 * Builds a query string for analytics filters.
 *
 * Purpose:
 * Converts optional dashboard filters into URL query parameters.
 *
 * Parameters:
 * @param {Record<string, string>} params Date, agent, category, and status filters.
 *
 * Returns:
 * Query string beginning with "?" or an empty string.
 *
 * Business Logic:
 * Empty filter values are omitted so the backend applies default reporting scope.
 */
function buildQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value)
    }
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

/**
 * Fetches role-aware analytics dashboard metrics.
 *
 * Purpose:
 * Loads totals, summaries, and chart data for the analytics page.
 *
 * Parameters:
 * @param {Record<string, string>} params Optional dashboard filters.
 *
 * Returns:
 * Parsed analytics dashboard payload.
 *
 * Business Logic:
 * The backend enforces role scoping, including personal-only analytics for agents.
 */
export async function fetchAnalyticsDashboard(params = {}) {
  const response = await fetch(`${API_BASE_URL}/analytics/dashboard${buildQuery(params)}`, {
    credentials: 'include',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.message || 'Unable to load analytics')
  }
  return data
}

/**
 * Downloads the filtered analytics Excel workbook.
 *
 * Purpose:
 * Retrieves the production XLSX report with raw data, summaries, and charts.
 *
 * Parameters:
 * @param {Record<string, string>} params Optional dashboard filters.
 *
 * Returns:
 * Blob containing the Excel workbook.
 *
 * Business Logic:
 * Uses the same filters as the dashboard so exported values match visible metrics.
 */
export async function exportAnalyticsDashboard(params = {}) {
  const response = await fetch(`${API_BASE_URL}/analytics/dashboard/export${buildQuery(params)}`, {
    credentials: 'include',
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || data.message || 'Unable to export analytics')
  }
  return response.blob()
}

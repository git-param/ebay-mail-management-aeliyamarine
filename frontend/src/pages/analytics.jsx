import { useEffect, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { exportAnalyticsDashboard, fetchAnalyticsDashboard } from '../services/analyticsApi'
import { fetchCategories } from '../services/categoryApi'
import { fetchUsers } from '../services/userApi'

function numericValue(value) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : 0
}

function MetricCard({ label, value }) {
  return (
    <article className="stat-card">
      <div>
        <p>{label}</p>
        <strong>{value ?? 0}</strong>
      </div>
    </article>
  )
}

function graphDescription(title) {
  const descriptions = {
    'Agent Productivity': {
      purpose: 'Shows how many conversations are currently assigned to each agent.',
      parameters: 'Agent = current assignee. Value = conversation count.',
    },
    'Category Distribution': {
      purpose: 'Shows conversation volume by category.',
      parameters: 'Category = assigned conversation category. Value = conversation count.',
    },
    'SLA Compliance': {
      purpose: 'Shows whether conversations are within the configured response SLA.',
      parameters: 'Compliant = first response within SLA. Breached = first response late or currently overdue.',
    },
    'Daily Trend': {
      purpose: 'Shows conversation volume over time.',
      parameters: 'Date = latest message date. Value = number of conversations on that date.',
    },
  }
  return descriptions[title] || { purpose: 'Shows filtered analytics data.', parameters: 'Values use the active dashboard filters.' }
}

function GraphInfo({ title }) {
  const description = graphDescription(title)
  return (
    <span className="graph-info" tabIndex={0} aria-label={`${title} details`}>
      i
      <span className="graph-tooltip" role="tooltip">
        <strong>{title}</strong>
        <span>{description.purpose}</span>
        <span>{description.parameters}</span>
      </span>
    </span>
  )
}

/**
 * Renders a small pie-style split for SLA compliance.
 *
 * Purpose:
 * Gives operations users a quick visual of compliant versus breached SLA work.
 *
 * Parameters:
 * @param {{items: Array<{label: string, value: number|string}>}} props SLA metric rows.
 *
 * Returns:
 * React section containing a CSS pie and legend.
 *
 * Business Logic:
 * Only compliant and breached rows are included in the pie split; open overdue
 * remains visible in the legend for operational attention.
 */
function PieChart({ items }) {
  const compliant = Number(items?.find((item) => item.label === 'Compliant')?.value || 0)
  const breached = Number(items?.find((item) => item.label === 'Breached')?.value || 0)
  const total = compliant + breached
  const percent = total ? Math.round((compliant / total) * 100) : 0
  return (
    <section className="analytics-panel analytics-pie-panel">
      <h2>SLA Compliance <GraphInfo title="SLA Compliance" /></h2>
      <div className="analytics-pie" style={{ '--pie-value': `${percent}%` }}>
        <strong>{total ? `${percent}%` : 'N/A'}</strong>
        <span>Compliant</span>
      </div>
      <div className="analytics-list">
        {(items || []).map((item) => (
          <div key={`sla-${item.label}`}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}

function BarChart({ title, items }) {
  const maxValue = Math.max(...(items || []).map((item) => numericValue(item.value)), 1)
  return (
    <section className="analytics-panel analytics-chart-panel">
      <h2>{title} <GraphInfo title={title} /></h2>
      {items?.length ? (
        <div className="analytics-bars">
          {items.slice(0, 8).map((item) => {
            const value = numericValue(item.value)
            return (
              <div className="analytics-bar-row" key={`${title}-${item.label}`}>
                <span>{item.label}</span>
                <div className="analytics-bar-track">
                  <span style={{ width: `${Math.max((value / maxValue) * 100, 3)}%` }} />
                </div>
                <strong>{item.value}</strong>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="detail-muted">No data available.</p>
      )}
    </section>
  )
}

function TrendChart({ items }) {
  const values = (items || []).slice(-14).map((item) => numericValue(item.value))
  const maxValue = Math.max(...values, 1)
  return (
    <section className="analytics-panel analytics-trend-panel">
      <div>
        <h2>Daily Trend <GraphInfo title="Daily Trend" /></h2>
        <p>Last {values.length || 0} recorded days</p>
      </div>
      {values.length ? (
        <div className="trend-chart" aria-label="Daily conversation trend">
          {items.slice(-14).map((item) => (
            <div className="trend-chart-item" key={item.label} title={`${item.label}: ${item.value} conversations`}>
              <strong>{item.value}</strong>
              <span style={{ height: `${Math.max((numericValue(item.value) / maxValue) * 100, 8)}%` }} />
              <small>{item.label.slice(5)}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="detail-muted">No trend data yet.</p>
      )}
    </section>
  )
}

function MetricList({ title, items }) {
  return (
    <section className="analytics-panel">
      <h2>{title}</h2>
      {items?.length ? (
        <div className="analytics-list">
          {items.map((item) => (
            <div key={`${title}-${item.label}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      ) : (
        <p className="detail-muted">No data available.</p>
      )}
    </section>
  )
}

/**
 * Renders analytics filters.
 *
 * Purpose:
 * Lets admins and operations managers slice analytics by date, agent,
 * category, and status.
 *
 * Parameters:
 * @param {object} props Filter state, support data, and event handlers.
 *
 * Returns:
 * React form controls for analytics filtering.
 *
 * Business Logic:
 * Agent options are hidden for personal agent dashboards because the backend
 * enforces the logged-in agent scope.
 */
function AnalyticsFilters({ filters, users, categories, showAgentFilter, onChange, onApply, onReset }) {
  return (
    <form className="analytics-filter-bar" onSubmit={onApply}>
      <label className="field">
        <span>From Date</span>
        <input type="date" value={filters.start_date} onChange={(event) => onChange('start_date', event.target.value)} />
      </label>
      <label className="field">
        <span>To Date</span>
        <input type="date" value={filters.end_date} onChange={(event) => onChange('end_date', event.target.value)} />
      </label>
      {showAgentFilter ? (
        <label className="field">
          <span>Agent</span>
          <select value={filters.agent_id} onChange={(event) => onChange('agent_id', event.target.value)}>
            <option value="">All agents</option>
            {users.map((user) => (
              <option value={user.id} key={user.id}>
                {user.full_name || user.fullName || user.email}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="field">
        <span>Category</span>
        <select value={filters.category_id} onChange={(event) => onChange('category_id', event.target.value)}>
          <option value="">All categories</option>
          {categories.map((category) => (
            <option value={category.id} key={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Status</span>
        <select value={filters.status} onChange={(event) => onChange('status', event.target.value)}>
          <option value="">All statuses</option>
          {['OPEN', 'PENDING', 'RESOLVED', 'CLOSED'].map((status) => (
            <option value={status} key={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
      <div className="analytics-filter-actions">
        <button className="secondary-button compact-action" type="button" onClick={onReset}>
          Reset
        </button>
        <button className="primary-button compact" type="submit">
          Apply
        </button>
      </div>
    </form>
  )
}

function Analytics({ currentUser, onLogout }) {
  const [dashboard, setDashboard] = useState(null)
  const [filters, setFilters] = useState({
    start_date: '',
    end_date: '',
    agent_id: '',
    category_id: '',
    status: '',
  })
  const [users, setUsers] = useState([])
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isExporting, setIsExporting] = useState(false)

  /**
   * Loads the analytics dashboard from the backend.
   *
   * Purpose:
   * Refreshes metrics and chart datasets using the current filter state.
   *
   * Parameters:
   * None.
   *
   * Returns:
   * Promise that resolves when state has been updated.
   *
   * Business Logic:
   * Filter state is passed directly to the API; empty fields are omitted by
   * the analytics service client.
   */
  async function loadDashboard(nextFilters = filters) {
    setIsLoading(true)
    setError('')
    try {
      setDashboard(await fetchAnalyticsDashboard(nextFilters))
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * Loads filter dropdown data.
   *
   * Purpose:
   * Provides agent and category choices for analytics filters.
   *
   * Parameters:
   * None.
   *
   * Returns:
   * Promise that resolves after support data is loaded.
   *
   * Business Logic:
   * Support-data failures do not block dashboard metrics; unavailable lists
   * simply render empty dropdowns.
   */
  async function loadSupportData() {
    const [userResult, categoryResult] = await Promise.allSettled([fetchUsers(), fetchCategories()])
    if (userResult.status === 'fulfilled') {
      setUsers(userResult.value.items || userResult.value.users || userResult.value || [])
    }
    if (categoryResult.status === 'fulfilled') {
      setCategories(categoryResult.value.items || categoryResult.value.categories || categoryResult.value || [])
    }
  }

  /**
   * Updates one analytics filter field.
   *
   * Purpose:
   * Keeps the filter form controlled and predictable.
   *
   * Parameters:
   * @param {string} key Filter field name.
   * @param {string} value Filter field value.
   *
   * Returns:
   * None.
   *
   * Business Logic:
   * Filter application happens on submit so users can adjust several fields
   * before refreshing the report.
   */
  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  /**
   * Applies analytics filters.
   *
   * Purpose:
   * Prevents full page reload and refreshes the dashboard.
   *
   * Parameters:
   * @param {SubmitEvent} event Form submit event.
   *
   * Returns:
   * None.
   *
   * Business Logic:
   * The existing filter state is reused by loadDashboard.
   */
  function applyFilters(event) {
    event.preventDefault()
    loadDashboard()
  }

  /**
   * Clears analytics filters and reloads the dashboard.
   *
   * Purpose:
   * Gives users a quick way back to the default reporting scope.
   *
   * Parameters:
   * None.
   *
   * Returns:
   * None.
   *
   * Business Logic:
   * Agent users remain personally scoped by the backend after reset.
   */
  function resetFilters() {
    const nextFilters = {
      start_date: '',
      end_date: '',
      agent_id: '',
      category_id: '',
      status: '',
    }
    setFilters(nextFilters)
    loadDashboard(nextFilters)
  }

  /**
   * Downloads the filtered Excel report.
   *
   * Purpose:
   * Saves the generated XLSX workbook returned by the backend.
   *
   * Parameters:
   * None.
   *
   * Returns:
   * Promise that resolves after the browser download is triggered.
   *
   * Business Logic:
   * The export uses the same filters currently applied on the dashboard.
   */
  async function downloadExport() {
    setIsExporting(true)
    setError('')
    try {
      const blob = await exportAnalyticsDashboard(filters)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'conversation_analytics.xlsx'
      link.click()
      window.URL.revokeObjectURL(url)
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsExporting(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadSupportData()
      loadDashboard()
    }, 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const showAgentFilter = dashboard?.role_scope !== 'AGENT'

  return (
    <AppLayout activePage="Analytics" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Analytics</h1>
            <p>{dashboard?.role_scope === 'AGENT' ? 'Personal performance' : dashboard?.role_scope === 'ADMIN' ? 'Business overview' : 'Operational performance'}</p>
          </div>
          <div className="header-actions">
            <button className="secondary-button compact-action" type="button" onClick={downloadExport} disabled={isExporting}>
              {isExporting ? 'Exporting...' : 'Export Excel'}
            </button>
            <button className="secondary-button compact-action" type="button" onClick={loadDashboard}>
              Refresh
            </button>
          </div>
        </div>

        <AnalyticsFilters
          filters={filters}
          users={users}
          categories={categories}
          showAgentFilter={showAgentFilter}
          onChange={updateFilter}
          onApply={applyFilters}
          onReset={resetFilters}
        />

        {error ? <p className="form-message error management-error">{error}</p> : null}
        {isLoading ? <div className="empty-state"><h2>Loading analytics...</h2></div> : null}

        {dashboard ? (
          <>
            <section className="stats-grid analytics-stats-grid">
              {dashboard.totals.map((item) => (
                <MetricCard label={item.label} value={item.value} key={item.label} />
              ))}
            </section>
            <div className="analytics-feature-grid">
              <BarChart title="Agent Productivity" items={dashboard.agent_productivity || dashboard.by_assigned_user} />
              <BarChart title="Category Distribution" items={dashboard.category_distribution || dashboard.by_category} />
              <PieChart items={dashboard.sla_metrics} />
              <TrendChart items={dashboard.daily_trends} />
            </div>
            <div className="analytics-grid">
              <MetricList title="Messages by Status" items={dashboard.by_status} />
              <MetricList title="Agent-wise Handling" items={(dashboard.agent_summary || []).map((item) => ({ label: item.Agent, value: `${item.Conversations} conv / ${item.Replies} replies` }))} />
              <MetricList title="Category-wise Handling" items={(dashboard.category_summary || []).map((item) => ({ label: item.Category, value: `${item.Conversations} conv / ${item['SLA Compliance']} SLA` }))} />
            </div>
          </>
        ) : null}
      </main>
    </AppLayout>
  )
}

export default Analytics

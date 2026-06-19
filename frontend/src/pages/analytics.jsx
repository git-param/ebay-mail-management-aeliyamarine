import { useEffect, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { fetchAnalyticsDashboard } from '../services/analyticsApi'

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

function BarChart({ title, items }) {
  const maxValue = Math.max(...(items || []).map((item) => numericValue(item.value)), 1)
  return (
    <section className="analytics-panel analytics-chart-panel">
      <h2>{title}</h2>
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
        <h2>Daily Trend</h2>
        <p>Last {values.length || 0} recorded days</p>
      </div>
      {values.length ? (
        <div className="trend-chart" aria-label="Daily message trend">
          {items.slice(-14).map((item) => (
            <span
              key={item.label}
              title={`${item.label}: ${item.value}`}
              style={{ height: `${Math.max((numericValue(item.value) / maxValue) * 100, 8)}%` }}
            />
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

function Analytics({ currentUser, onLogout }) {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  async function loadDashboard() {
    setIsLoading(true)
    setError('')
    try {
      setDashboard(await fetchAnalyticsDashboard())
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  return (
    <AppLayout activePage="Analytics" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Analytics</h1>
            <p>{dashboard?.role_scope === 'ADMIN' ? 'Business overview' : 'Operational performance'}</p>
          </div>
          <button className="secondary-button compact-action" type="button" onClick={loadDashboard}>
            Refresh
          </button>
        </div>

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
              <BarChart title="Messages by Category" items={dashboard.by_category} />
              <BarChart title="Agent Workload" items={dashboard.by_assigned_user} />
              <TrendChart items={dashboard.daily_trends} />
            </div>
            <div className="analytics-grid">
              <MetricList title="Messages by Status" items={dashboard.by_status} />
              <MetricList title="SLA Metrics" items={dashboard.sla_metrics} />
            </div>
          </>
        ) : null}
      </main>
    </AppLayout>
  )
}

export default Analytics

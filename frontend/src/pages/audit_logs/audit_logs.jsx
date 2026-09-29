import { useEffect, useState } from 'react'

import AppLayout from '../../layouts/app_layout'
import { exportAuditLogs, fetchAuditFilterOptions, fetchAuditLogs } from '../../services/auditApi'
import './audit_logs.css'

const PAGE_SIZE = 50
const EMPTY_OPTIONS = { categories: [], actions: [], statuses: [], entity_types: [] }
const readable = (value) => value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())

function formatDate(value) {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { timeZone: 'Asia/Kolkata' })
}

function formatTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' })
}

function AuditLogs({ currentUser, onLogout }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [filters, setFilters] = useState({ category: '', status: '', action: '', entity_type: '', date_from: '', date_to: '' })
  const [options, setOptions] = useState(EMPTY_OPTIONS)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  async function downloadExport() {
    try {
      const blob = await exportAuditLogs(filters)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'audit_logs.csv'
      link.click()
      window.URL.revokeObjectURL(url)
    } catch (caughtError) {
      setError(caughtError.message)
    }
  }

  useEffect(() => {
    let active = true
    fetchAuditLogs({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, ...filters })
      .then(response => {
        if (active) { setLogs(response.items || []); setTotal(response.total || 0); setError('') }
      })
      .catch(caughtError => {
        if (active) { setError(caughtError.message); setLogs([]); setTotal(0) }
      })
      .finally(() => { if (active) setIsLoading(false) })
    return () => { active = false }
  }, [page, filters])

  useEffect(() => {
    fetchAuditFilterOptions().then(setOptions).catch((caughtError) => setError(caughtError.message))
  }, [])

  function updateFilter(key, value) {
    setIsLoading(true)
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(0)
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const firstEvent = total ? page * PAGE_SIZE + 1 : 0
  const lastEvent = Math.min((page + 1) * PAGE_SIZE, total)
  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <AppLayout activePage="Audit Logs" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page audit-page">
        <div className="page-header">
          <div>
            <h1>Audit Logs</h1>
            <p>{total.toLocaleString()} events · All times in India time</p>
          </div>
          <div className="audit-header-actions">
          {hasFilters ? <button className="secondary-button compact-action" type="button" onClick={() => { setIsLoading(true); setPage(0); setFilters({ category: '', status: '', action: '', entity_type: '', date_from: '', date_to: '' }) }}>Clear filters</button> : null}
          <button className="secondary-button compact-action" type="button" onClick={downloadExport}>
            Export CSV
          </button>
          </div>
        </div>

        <section className="filter-panel">
          <label className="field">
            <span>Category</span>
            <select value={filters.category} onChange={(event) => updateFilter('category', event.target.value)}>
              <option value="">All Categories</option>
              {options.categories.map((value) => <option value={value} key={value}>{readable(value)}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Status</span>
            <select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}>
              <option value="">All Statuses</option>
              {options.statuses.map((value) => <option value={value} key={value}>{readable(value)}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Action</span>
            <select value={filters.action} onChange={(event) => updateFilter('action', event.target.value)}>
              <option value="">All Actions</option>
              {options.actions.map((value) => <option value={value} key={value}>{readable(value)}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Resource Type</span>
            <select value={filters.entity_type} onChange={(event) => updateFilter('entity_type', event.target.value)}>
              <option value="">All Resource Types</option>
              {options.entity_types.map((value) => <option value={value} key={value}>{readable(value)}</option>)}
            </select>
          </label>
          <label className="field"><span>From (India time)</span><input type="date" max={filters.date_to || undefined} value={filters.date_from} onChange={(event) => updateFilter('date_from', event.target.value)} /></label>
          <label className="field"><span>To (India time)</span><input type="date" min={filters.date_from || undefined} value={filters.date_to} onChange={(event) => updateFilter('date_to', event.target.value)} /></label>
        </section>

        {error ? <p className="form-message error management-error">{error}</p> : null}

        <section className="table-card">
          {isLoading ? (
            <div className="empty-state"><h2>Loading audit logs...</h2></div>
          ) : (
            <div className="table-scroll" tabIndex={0} role="region" aria-label="Audit events, scroll to see all columns">
              <table className="users-table" aria-label="Audit activity">
                <colgroup>{['date', 'time', 'user', 'role', 'action', 'module', 'resource', 'details', 'status'].map(column => <col key={column} className={`audit-column-${column}`} />)}</colgroup>
                <thead>
                  <tr>
                    <th>Date</th><th>Time</th>
                    <th>User</th>
                    <th>Role</th><th>Action</th><th>Module</th><th>Resource</th><th>Details</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.created_at)}</td><td>{formatTime(log.created_at)}</td>
                      <td>{log.actor_name || log.user?.name || log.user?.email || 'System'}</td><td>{log.metadata?.actor_role || log.user?.role || 'System'}</td>
                      <td>{log.action_label}</td><td>{log.module_label}</td><td>{log.resource_label}</td><td><p className="audit-description">{log.details}</p>{log.conversation_id || log.entity_id ? <details className="audit-record-ids"><summary>Record IDs</summary>{log.conversation_id ? <div>Conversation: <code>{log.conversation_id}</code></div> : null}{log.entity_id && log.entity_id !== log.conversation_id ? <div>{readable(log.entity_type || 'Resource')}: <code>{log.entity_id}</code></div> : null}</details> : null}</td>
                      <td><span className={`audit-status audit-status-${String(log.status || 'unknown').toLowerCase().replace(/[^a-z]/g, '')}`}>{log.status ? readable(log.status) : 'Not recorded'}</span></td>
                    </tr>
                  ))}
                  {!logs.length ? <tr><td colSpan={9} className="audit-empty">No audit events match these filters.</td></tr> : null}
                </tbody>
              </table>
            </div>
          )}
        <div className="pagination-bar audit-pagination">
          <span className="audit-results-count" role="status">{isLoading ? 'Loading events...' : `Showing ${firstEvent.toLocaleString()}–${lastEvent.toLocaleString()} of ${total.toLocaleString()} events`}</span>
          <nav className="audit-pagination-controls" aria-label="Audit log pages">
          <button className="secondary-button" type="button" disabled={isLoading || page === 0} onClick={() => { setIsLoading(true); setPage(page - 1) }}>Previous</button>
          <span>Page {page + 1} of {pageCount}</span>
          <button className="secondary-button" type="button" disabled={isLoading || page + 1 >= pageCount} onClick={() => { setIsLoading(true); setPage(page + 1) }}>Next</button>
          </nav>
        </div>
        </section>
      </main>
    </AppLayout>
  )
}

export default AuditLogs

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
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

function formatTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function AuditLogs({ currentUser, onLogout }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [filters, setFilters] = useState({ category: '', status: '', action: '', entity_type: '', date_from: '', date_to: '' })
  const [options, setOptions] = useState(EMPTY_OPTIONS)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  async function loadLogs() {
    setIsLoading(true)
    setError('')
    try {
      const response = await fetchAuditLogs({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        ...filters,
      })
      setLogs(response.items || [])
      setTotal(response.total || 0)
    } catch (caughtError) {
      setError(caughtError.message)
      setLogs([])
      setTotal(0)
    } finally {
      setIsLoading(false)
    }
  }

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
    loadLogs()
  }, [page, filters])

  useEffect(() => {
    fetchAuditFilterOptions().then(setOptions).catch((caughtError) => setError(caughtError.message))
  }, [])

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(0)
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppLayout activePage="Audit Logs" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page audit-page">
        <div className="page-header">
          <div>
            <h1>Audit Logs</h1>
            <p>{total} events</p>
          </div>
          <button className="secondary-button compact-action" type="button" onClick={downloadExport}>
            Export CSV
          </button>
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
          <label className="field"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => updateFilter('date_from', event.target.value)} /></label>
          <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => updateFilter('date_to', event.target.value)} /></label>
        </section>

        {error ? <p className="form-message error management-error">{error}</p> : null}

        <section className="table-card">
          {isLoading ? (
            <div className="empty-state"><h2>Loading audit logs...</h2></div>
          ) : (
            <div className="table-scroll">
              <table className="users-table">
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
                      <td>{log.user?.name || log.user?.email || 'System'}</td><td>{log.user?.role || 'System'}</td>
                      <td>{log.action_label}</td><td>{log.module_label}</td><td>{log.resource_label}</td><td title={log.details}>{log.details}</td>
                      <td>{log.status || '-'}</td>
                    </tr>
                  ))}
                  {!logs.length ? <tr><td colSpan={9} className="audit-empty">No audit events match these filters.</td></tr> : null}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="pagination-bar">
          <button className="secondary-button" type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page + 1} of {pageCount}</span>
          <button className="secondary-button" type="button" disabled={page + 1 >= pageCount} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </main>
    </AppLayout>
  )
}

export default AuditLogs

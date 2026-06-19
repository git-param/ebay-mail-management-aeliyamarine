import { useEffect, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { exportAuditLogs, fetchAuditLogs } from '../services/auditApi'

const PAGE_SIZE = 50
const CATEGORIES = ['', 'AUTHENTICATION', 'ASSIGNMENT', 'EBAY', 'CATEGORY_MANAGEMENT', 'USER_MANAGEMENT', 'SYNC', 'NOTIFICATION', 'MESSAGE_MANAGEMENT']
const STATUSES = ['', 'SUCCESS', 'FAILURE']

function formatDate(value) {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function AuditLogs({ currentUser, onLogout }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [filters, setFilters] = useState({ category: '', status: '', action: '', entity_type: '' })
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
      const blob = await exportAuditLogs()
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

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(0)
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <AppLayout activePage="Audit Logs" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
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
              {CATEGORIES.map((value) => <option value={value} key={value}>{value || 'All Categories'}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Status</span>
            <select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)}>
              {STATUSES.map((value) => <option value={value} key={value}>{value || 'All Statuses'}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Action</span>
            <input value={filters.action} onChange={(event) => updateFilter('action', event.target.value)} placeholder="LOGIN_SUCCESS" />
          </label>
          <label className="field">
            <span>Resource Type</span>
            <input value={filters.entity_type} onChange={(event) => updateFilter('entity_type', event.target.value)} placeholder="CONVERSATION" />
          </label>
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
                    <th>Time</th>
                    <th>User</th>
                    <th>Action</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th>Resource</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.created_at)}</td>
                      <td>{log.user?.email || 'System'}</td>
                      <td>{log.action}</td>
                      <td>{log.category || '-'}</td>
                      <td>{log.status || '-'}</td>
                      <td>{log.entity_type || '-'} {log.entity_id || ''}</td>
                    </tr>
                  ))}
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

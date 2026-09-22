import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { exportBreakReport, fetchBreakEmployees, fetchBreakHistory, fetchBreakOverview } from '../../services/breakManagementApi'
import { normalizeRole } from '../../utils/roles'
import BreakActionButton from './BreakActionButton'

import './break_maagement.css'

const QUICK_RANGES = {
  today: 'Today',
  yesterday: 'Yesterday',
  custom: 'Custom Date Range',
}

function isoDate(date) {
  return date.toISOString().slice(0, 10)
}

function defaultFilters() {
  const today = new Date()
  return {
    preset: 'today',
    date_from: isoDate(today),
    date_to: isoDate(today),
  }
}

function minutesLabel(value) {
  const minutes = Number(value || 0)
  return `${minutes} min${minutes === 1 ? '' : 's'}`
}

function dateLabel(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

function timeLabel(value) {
  if (!value) return '-'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function applyPreset(preset) {
  const today = new Date()
  if (preset === 'yesterday') {
    today.setDate(today.getDate() - 1)
  }
  return {
    preset,
    date_from: isoDate(today),
    date_to: isoDate(today),
  }
}

function BreakHistoryTable({ items, emptyText = 'No breaks found for this date range.' }) {
  return (
    <div className="breakModule-table-wrap">
      <table className="breakModule-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Start Time</th>
            <th>End Time</th>
            <th>Duration (mins)</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{dateLabel(item.start_time)}</td>
              <td>{timeLabel(item.start_time)}</td>
              <td>{timeLabel(item.end_time)}</td>
              <td>{item.duration_minutes ?? 0}</td>
              <td>{item.reason}</td>
            </tr>
          ))}
          {!items.length ? (
            <tr>
              <td colSpan={5}>
                <div className="breakModule-empty">{emptyText}</div>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function DateRangeControls({ filters, onChange }) {
  return (
    <div className="breakModule-date-controls">
      <select value={filters.preset} onChange={(event) => onChange(applyPreset(event.target.value))}>
        {Object.entries(QUICK_RANGES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input
        type="date"
        value={filters.date_from}
        onChange={(event) => onChange({ ...filters, preset: 'custom', date_from: event.target.value })}
      />
      <input
        type="date"
        value={filters.date_to}
        onChange={(event) => onChange({ ...filters, preset: 'custom', date_to: event.target.value })}
      />
    </div>
  )
}

function UserBreakCard({ user, onOpen }) {
  return (
    <button className={`breakModule-user-card ${user.is_on_break ? 'on-break' : 'active'}`} type="button" onClick={() => onOpen(user)}>
      <span className="breakModule-card-state">{user.is_on_break ? 'On Break' : 'Active'}</span>
      <strong>{user.user_name}</strong>
      <span>Total Break Time: {minutesLabel(user.total_break_minutes_today)}</span>
      {user.is_on_break ? <small>Status: {user.active_reason || 'Break'}</small> : null}
    </button>
  )
}

function UserHistoryModal({ user, onClose }) {
  const [filters, setFilters] = useState(defaultFilters)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchBreakHistory({
      user_id: user.user_id,
      date_from: filters.date_from,
      date_to: filters.date_to,
    })
      .then((response) => {
        if (active) setItems(response.items || [])
      })
      .catch((caughtError) => {
        if (active) setError(caughtError.message || 'Unable to load break history.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [user.user_id, filters.date_from, filters.date_to])

  return (
    <div className="breakModule-detail-backdrop">
      <section className="breakModule-detail-modal">
        <div className="breakModule-detail-header">
          <div>
            <span>Employee Break History Table</span>
            <h2>{user.user_name}</h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <DateRangeControls filters={filters} onChange={setFilters} />
        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading ? <div className="breakModule-empty">Loading break history...</div> : <BreakHistoryTable items={items} />}
      </section>
    </div>
  )
}

function AgentBreakView() {
  const [filters, setFilters] = useState(defaultFilters)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchBreakHistory({ date_from: filters.date_from, date_to: filters.date_to })
      .then((response) => {
        if (active) setItems(response.items || [])
      })
      .catch((caughtError) => {
        if (active) setError(caughtError.message || 'Unable to load your break history.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [filters.date_from, filters.date_to])

  const totalMinutes = useMemo(() => items.reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0), [items])

  return (
    <>
      <section className="breakModule-summary-band">
        <div>
          <span>Breaks in range</span>
          <strong>{items.length}</strong>
        </div>
        <div>
          <span>Total duration</span>
          <strong>{minutesLabel(totalMinutes)}</strong>
        </div>
      </section>
      <section className="breakModule-panel">
        <div className="breakModule-panel-header">
          <div>
            <h2>Personal Break History</h2>
            <p>Daily break entries and reasons from your audit trail.</p>
          </div>
          <DateRangeControls filters={filters} onChange={setFilters} />
        </div>
        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading ? <div className="breakModule-empty">Loading break history...</div> : <BreakHistoryTable items={items} />}
      </section>
    </>
  )
}

function BreakExportDialog({ onClose }) {
  const [employees, setEmployees] = useState([])
  const [selection, setSelection] = useState('all')
  const [selectedIds, setSelectedIds] = useState([])
  const [filters, setFilters] = useState(defaultFilters)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchBreakEmployees()
      .then((response) => setEmployees(response.items || []))
      .catch((caughtError) => setError(caughtError.message || 'Unable to load employees.'))
  }, [])

  function toggleEmployee(id) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  async function download(event) {
    event.preventDefault()
    if (filters.date_from > filters.date_to) {
      setError('Start date must be on or before end date.')
      return
    }
    if (selection === 'selected' && !selectedIds.length) {
      setError('Select at least one employee.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const blob = await exportBreakReport({
        date_from: filters.date_from,
        date_to: filters.date_to,
        user_ids: selection === 'all' ? undefined : selectedIds,
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `break_report_${filters.date_from}_${filters.date_to}.xlsx`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
      onClose()
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to export break report.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="breakModule-modal-backdrop">
      <form className="breakModule-export-modal" onSubmit={download}>
        <div className="breakModule-modal-header">
          <div><h2>Export Break Report</h2></div>
          <button type="button" aria-label="Close" onClick={onClose}><Icon name="close" /></button>
        </div>
        <fieldset className="breakModule-export-fieldset">
          <legend>Employees</legend>
          <label><input type="radio" name="employeeSelection" checked={selection === 'all'} onChange={() => setSelection('all')} /> All employees</label>
          <label><input type="radio" name="employeeSelection" checked={selection === 'selected'} onChange={() => setSelection('selected')} /> Select employees</label>
          {selection === 'selected' ? (
            <div className="breakModule-employee-list">
              {employees.map((employee) => (
                <label key={employee.id}>
                  <input type="checkbox" checked={selectedIds.includes(employee.id)} onChange={() => toggleEmployee(employee.id)} />
                  <span>{employee.name}</span><small>{employee.role.replaceAll('_', ' ')}</small>
                </label>
              ))}
              {!employees.length ? <span>No employees available.</span> : null}
            </div>
          ) : null}
        </fieldset>
        <div className="breakModule-export-dates">
          <label>From<input type="date" required value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
          <label>To<input type="date" required value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
        </div>
        {error ? <p className="breakModule-message error" role="alert">{error}</p> : null}
        <div className="breakModule-modal-actions">
          <button className="breakModule-secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="breakModule-primary" type="submit" disabled={busy}>{busy ? 'Preparing...' : 'Download Excel'}</button>
        </div>
      </form>
    </div>
  )
}

function ManagerBreakView() {
  const [overview, setOverview] = useState({ sections: [] })
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [exportOpen, setExportOpen] = useState(false)

  async function loadOverview() {
    setLoading(true)
    setError('')
    try {
      const response = await fetchBreakOverview()
      setOverview(response)
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to load break overview.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOverview()
  }, [])

  return (
    <>
      <section className="breakModule-panel breakModule-overview">
        <div className="breakModule-panel-header">
          <div>
            <h2>Employee Break Status - Today</h2>
            <p>Live role-wise break visibility for admins, ops managers, and agents.</p>
          </div>
          <div className="breakModule-header-actions">
            <button className="breakModule-secondary" type="button" onClick={() => setExportOpen(true)}>Export Excel</button>
            <button className="breakModule-secondary" type="button" onClick={loadOverview}>
              <Icon name="refresh" /> Refresh
            </button>
          </div>
        </div>
        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading ? <div className="breakModule-empty">Loading employee break status...</div> : null}
        {!loading && overview.sections?.map((section) => (
          <section className="breakModule-role-section" key={section.role_key}>
            <h3>{section.title}</h3>
            <div className="breakModule-card-row">
              {section.users.map((user) => <UserBreakCard key={user.user_id} user={user} onOpen={setSelectedUser} />)}
            </div>
          </section>
        ))}
      </section>
      {selectedUser ? <UserHistoryModal user={selectedUser} onClose={() => setSelectedUser(null)} /> : null}
      {exportOpen ? <BreakExportDialog onClose={() => setExportOpen(false)} /> : null}
    </>
  )
}

function BreakManagement({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role)
  const isManagerView = ['ADMIN', 'OPS_MANAGER'].includes(role)

  return (
    <AppLayout activePage="Breaks" currentUser={currentUser} onLogout={onLogout}>
      <main className="breakModule-page">
        <header className="breakModule-header">
          <div>
            <span>Workforce Operations</span>
            <h1>Break Management</h1>
            <p>Track break status, durations, reasons, and immutable start/end audit events.</p>
          </div>
          <BreakActionButton />
        </header>
        {isManagerView ? <ManagerBreakView /> : <AgentBreakView />}
      </main>
    </AppLayout>
  )
}

export default BreakManagement

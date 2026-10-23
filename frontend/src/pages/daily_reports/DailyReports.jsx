import { useEffect, useState } from 'react'

import AppLayout from '../../layouts/app_layout'
import { fetchDailyReports, fetchDailyReportUsers, fetchTodayReport, saveAndCopyTodayReport, saveDailyTasks } from '../../services/dailyReportApi'
import { normalizeRole } from '../../utils/roles'

import './dailyReports.css'


const EMPTY_TASK = { name: '', quantity: 1 }

function formatDate(value) {
  return value ? value.split('-').reverse().join('-') : ''
}

export default function DailyReports({ currentUser, onLogout }) {
  const canViewAll = ['ADMIN', 'OPS_MANAGER'].includes(normalizeRole(currentUser?.role))
  const [today, setToday] = useState(null)
  const [reports, setReports] = useState([])
  const [total, setTotal] = useState(0)
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [appliedFilters, setAppliedFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [taskDraft, setTaskDraft] = useState(null)
  const [editingIndex, setEditingIndex] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadReports(nextFilters = appliedFilters, offset = 0) {
    const result = await fetchDailyReports({ ...nextFilters, limit: 50, offset })
    setReports((current) => offset ? [...current, ...result.items] : result.items)
    setTotal(result.total)
  }

  useEffect(() => {
    let active = true
    Promise.all([fetchTodayReport(), fetchDailyReports({ limit: 50, offset: 0 }),
      canViewAll ? fetchDailyReportUsers() : Promise.resolve([])])
      .then(([todayResult, historyResult, userResult]) => {
        if (!active) return
        setToday(todayResult)
        setReports(historyResult.items)
        setTotal(historyResult.total)
        setUsers(userResult)
      })
      .catch((caught) => { if (active) setError(caught.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [canViewAll])

  async function saveTask(event) {
    event.preventDefault()
    if (!today || busy) return
    const name = taskDraft.name.trim().replace(/\s+/g, ' ')
    const quantity = Number(taskDraft.quantity)
    if (!name || !Number.isInteger(quantity) || quantity < 1) {
      setError('Enter a task name and a quantity of at least 1.')
      return
    }
    const nextTasks = [...today.additional_tasks]
    if (editingIndex == null) nextTasks.push({ name, quantity })
    else nextTasks[editingIndex] = { name, quantity }
    await persistTasks(nextTasks)
  }

  async function persistTasks(tasks) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveDailyTasks(today.report_date, tasks)
      setToday(saved)
      setTaskDraft(null)
      setEditingIndex(null)
      setNotice('Today’s tasks were saved.')
      await loadReports()
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function copyToday() {
    if (!today || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveAndCopyTodayReport(today.report_date)
      setToday(saved)
      await loadReports()
      try {
        await navigator.clipboard.writeText(saved.report_text)
        setNotice('Today’s report was saved and copied.')
      } catch {
        setError('Today’s report was saved, but the browser could not copy it to the clipboard.')
      }
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function applyFilters(event) {
    event.preventDefault()
    setError('')
    try {
      await loadReports(filters)
      setAppliedFilters(filters)
    } catch (caught) {
      setError(caught.message)
    }
  }

  return (
    <AppLayout activePage="Daily Reports" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page daily-reports-page">
        <div className="page-header">
          <div>
            <h1>Daily Reports</h1>
            <p>Your message work and tasks completed outside the app, saved by day.</p>
          </div>
        </div>

        {error ? <p className="form-message error" role="alert">{error}</p> : null}
        {notice ? <p className="form-message success" role="status">{notice}</p> : null}

        <section className="daily-report-card" aria-labelledby="today-report-heading">
          <div className="daily-report-heading">
            <div>
              <h2 id="today-report-heading">Today’s report</h2>
              <p>{today ? `${formatDate(today.report_date)} · ${today.user_name}` : 'Loading today’s work…'}</p>
            </div>
            <div className="daily-report-actions">
              <button className="secondary-button compact-action" type="button" disabled={!today || busy}
                onClick={() => { setEditingIndex(null); setTaskDraft({ ...EMPTY_TASK }) }}>
                Add Tasks
              </button>
              <button className="primary-button compact" type="button" disabled={!today || busy || Boolean(taskDraft)}
                onClick={copyToday}>
                Copy Today’s Stats
              </button>
            </div>
          </div>
          {today ? (
            <>
              <label className="daily-report-preview-label" htmlFor="daily-report-preview">Work report text</label>
              <textarea id="daily-report-preview" className="daily-report-preview" readOnly
                value={today.report_text} rows={Math.max(5, today.report_text.split('\n').length + 1)} />
              <p className="daily-report-hint">Copying saves this report in the database. Tasks added here are saved immediately. Reports from previous dates are read-only.</p>
              {today.additional_tasks.length ? (
                <ul className="daily-report-tasks">
                  {today.additional_tasks.map((task, index) => (
                    <li key={`${task.name}-${index}`}>
                      <span>{task.name}{task.quantity > 1 ? ` - ${task.quantity}` : ''}</span>
                      <div>
                        <button className="secondary-button compact-action" type="button" disabled={busy}
                          onClick={() => { setEditingIndex(index); setTaskDraft({ ...task }) }}>Edit</button>
                        <button className="secondary-button compact-action" type="button" disabled={busy}
                          onClick={() => persistTasks(today.additional_tasks.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              {taskDraft ? (
                <form className="daily-report-task-form" onSubmit={saveTask}>
                  <label className="field"><span>Task name</span>
                    <input type="text" maxLength={120} required value={taskDraft.name}
                      onChange={(event) => setTaskDraft((current) => ({ ...current, name: event.target.value }))} />
                  </label>
                  <label className="field"><span>Quantity</span>
                    <input type="number" min="1" max="100000" required value={taskDraft.quantity}
                      onChange={(event) => setTaskDraft((current) => ({ ...current, quantity: event.target.value }))} />
                  </label>
                  <button className="primary-button compact" type="submit" disabled={busy}>{editingIndex == null ? 'Add Task' : 'Save Task'}</button>
                  <button className="secondary-button compact-action" type="button" disabled={busy}
                    onClick={() => { setTaskDraft(null); setEditingIndex(null) }}>Cancel</button>
                </form>
              ) : null}
            </>
          ) : <p>{loading ? 'Loading…' : 'Today’s report is unavailable.'}</p>}
        </section>

        <section className="daily-report-card" aria-labelledby="saved-reports-heading">
          <div className="daily-report-heading"><h2 id="saved-reports-heading">Saved reports</h2><span>{total} total</span></div>
          <form className="daily-report-filters" onSubmit={applyFilters}>
            <label className="field"><span>From</span><input type="date" value={filters.date_from}
              onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
            <label className="field"><span>To</span><input type="date" value={filters.date_to}
              onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
            {canViewAll ? <label className="field"><span>User</span><select value={filters.user_id}
              onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}>
              <option value="">All users</option>
              {users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
            </select></label> : null}
            <button className="primary-button compact" type="submit">Apply</button>
          </form>
          <div className="daily-report-history">
            {reports.map((report) => (
              <article className="daily-report-history-item" key={report.id}>
                <div><strong>{formatDate(report.report_date)}</strong><span>{report.user_name}</span></div>
                <pre>{report.report_text}</pre>
                <small>{report.editable ? 'Today · editable' : 'Past date · read-only'}</small>
              </article>
            ))}
            {!loading && !reports.length ? <p>No reports match these filters.</p> : null}
          </div>
          {reports.length < total ? <button className="secondary-button compact-action" type="button"
            onClick={() => loadReports(appliedFilters, reports.length).catch((caught) => setError(caught.message))}>Load more</button> : null}
        </section>
      </main>
    </AppLayout>
  )
}

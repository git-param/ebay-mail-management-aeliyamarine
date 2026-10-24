import { useEffect, useMemo, useState } from 'react'
import AppLayout from '../../layouts/app_layout'
import { fetchDailyReports, fetchDailyReportUsers, fetchTodayReport, saveAndCopyTodayReport } from '../../services/dailyReportApi'
import { fetchMainTasks } from '../../services/taskManagementApi'
import { normalizeRole } from '../../utils/roles'
import './dailyReports.css'

const displayDate = (value) => value ? value.split('-').reverse().join('-') : ''

function initialQuantities(tasks, report) {
  const recorded = [...(report.automatic_tasks || []), ...(report.additional_tasks || [])]
  const byId = new Map(recorded.filter((item) => item.task_id).map((item) => [item.task_id, item]))
  return Object.fromEntries(tasks.map((task) => [task.id, {
    quantity: byId.get(task.id)?.quantity ?? 0,
    remarks: byId.get(task.id)?.remarks || '',
  }]))
}

function previewText(day, tasks, quantities) {
  const lines = [`Work Report: ${displayDate(day)}`, '']
  tasks.forEach((task) => {
    const quantity = Number(quantities[task.id]?.quantity || 0)
    if (!Number.isInteger(quantity) || quantity <= 0) return
    const remarks = task.source_type === 'OTHER' ? String(quantities[task.id]?.remarks || '').trim() : ''
    lines.push(`${task.name}${quantity === 1 ? '' : ` - ${quantity}`}${remarks ? ` (${remarks})` : ''}`)
  })
  return lines.join('\n').trimEnd()
}

export default function DailyReports({ currentUser, onLogout }) {
  const canViewAll = ['ADMIN', 'OPS_MANAGER'].includes(normalizeRole(currentUser?.role))
  const [today, setToday] = useState(null)
  const [mainTasks, setMainTasks] = useState([])
  const [quantities, setQuantities] = useState({})
  const [reports, setReports] = useState([])
  const [total, setTotal] = useState(0)
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [appliedFilters, setAppliedFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const activeTasks = useMemo(() => mainTasks.filter((task) => task.is_active), [mainTasks])
  const reportPreview = today ? previewText(today.report_date, activeTasks, quantities) : ''

  async function loadReports(nextFilters = appliedFilters, offset = 0) {
    const result = await fetchDailyReports({ ...nextFilters, limit: 50, offset })
    setReports((current) => offset ? [...current, ...result.items] : result.items)
    setTotal(result.total)
  }

  useEffect(() => {
    let active = true
    Promise.all([fetchTodayReport(), fetchDailyReports({ limit: 50, offset: 0 }),
      canViewAll ? fetchDailyReportUsers() : Promise.resolve([]), fetchMainTasks()])
      .then(([todayResult, historyResult, userResult, taskResult]) => {
        if (!active) return
        const available = taskResult.filter((task) => task.is_active)
        setToday(todayResult)
        setReports(historyResult.items)
        setTotal(historyResult.total)
        setUsers(userResult)
        setMainTasks(taskResult)
        setQuantities(initialQuantities(available, todayResult))
      }).catch((caught) => { if (active) setError(caught.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [canViewAll])

  function changeTask(taskId, field, value) {
    setQuantities((current) => ({ ...current, [taskId]: { ...current[taskId], [field]: value } }))
    setNotice('')
  }

  async function copyToday() {
    if (!today || busy) return
    const tasks = activeTasks.map((task) => ({ task_id: task.id,
      quantity: quantities[task.id]?.quantity === '' ? NaN : Number(quantities[task.id]?.quantity),
      remarks: task.source_type === 'OTHER' ? String(quantities[task.id]?.remarks || '').trim() : null }))
    if (tasks.some((task) => !Number.isInteger(task.quantity) || task.quantity < 0 || task.quantity > 100000)) {
      setError('Enter a whole-number quantity from 0 to 100,000 for every task.'); return
    }
    if (tasks.some((task) => activeTasks.find((item) => item.id === task.task_id)?.source_type === 'OTHER' && task.quantity > 0 && !task.remarks)) {
      setError('Add remarks when Other has a quantity above zero.'); return
    }
    setBusy(true); setError(''); setNotice('')
    try {
      const saved = await saveAndCopyTodayReport(today.report_date, tasks)
      setToday(saved)
      try {
        await navigator.clipboard.writeText(saved.report_text)
        setNotice('Today’s report was saved and copied.')
      } catch { setError('Today’s report was saved, but the browser could not copy it to the clipboard.') }
      await loadReports().catch((caught) => setError(`Today’s report was saved, but history could not refresh: ${caught.message}`))
    } catch (caught) { setError(caught.message) }
    finally { setBusy(false) }
  }

  async function applyFilters(event) {
    event.preventDefault(); setError('')
    try { await loadReports(filters); setAppliedFilters(filters) }
    catch (caught) { setError(caught.message) }
  }

  return <AppLayout activePage="Daily Reports" currentUser={currentUser} onLogout={onLogout}>
    <main className="management-page daily-reports-page">
      <div className="page-header"><div><h1>Daily Reports</h1><p>Review each task quantity before saving your work report.</p></div></div>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {notice ? <p className="form-message success" role="status">{notice}</p> : null}
      <section className="daily-report-card" aria-labelledby="today-report-heading">
        <div className="daily-report-heading"><div><h2 id="today-report-heading">Today’s report</h2>
          <p>{today ? `${displayDate(today.report_date)} · ${today.user_name}` : 'Loading today’s work…'}</p></div>
          <button className="primary-button compact" type="button" disabled={!today || busy || !activeTasks.length} onClick={copyToday}>{busy ? 'Saving…' : 'Copy Today’s Stats'}</button></div>
        {today ? <>
          <div className="daily-report-review-heading"><h3>Task quantities</h3><p>Automatic counts are filled in. Check each one and enter manual work. Set a task to 0 to leave it out.</p></div>
          <div className="daily-report-review-list">
            {activeTasks.map((task) => <div className="daily-report-review-row" key={task.id}>
              <div className="daily-report-review-name"><strong>{task.name}</strong><small>{task.source_type === 'OTHER' ? 'Other work' : task.source_type === 'MANUAL' ? 'Manual task' : 'Automatically counted'}</small></div>
              <label className="field daily-report-quantity"><span>Quantity</span><input type="number" min="0" max="100000" step="1" value={quantities[task.id]?.quantity ?? 0}
                onChange={(event) => changeTask(task.id, 'quantity', event.target.value)} /></label>
              {task.source_type === 'OTHER' && Number(quantities[task.id]?.quantity) > 0 ? <label className="field daily-report-other-remarks"><span>Other task remarks</span>
                <textarea maxLength="1000" placeholder="Describe the other work completed" value={quantities[task.id]?.remarks || ''}
                  onChange={(event) => changeTask(task.id, 'remarks', event.target.value)} /></label> : null}
            </div>)}
            {!activeTasks.length ? <p>No active tasks are configured yet.</p> : null}
          </div>
          <div className="daily-report-preview-section"><label className="daily-report-preview-label" htmlFor="daily-report-preview">Work report preview</label>
            <textarea id="daily-report-preview" className="daily-report-preview" readOnly value={reportPreview} rows={Math.max(4, reportPreview.split('\n').length + 1)} />
            <p className="daily-report-hint">Copy Today’s Stats saves these quantities for the day, then copies the report to your clipboard. Zero quantity tasks are omitted.</p></div>
        </> : <p>{loading ? 'Loading…' : 'Today’s report is unavailable.'}</p>}
      </section>
      <section className="daily-report-card" aria-labelledby="saved-reports-heading">
        <div className="daily-report-heading"><h2 id="saved-reports-heading">Saved reports</h2><span>{total} total</span></div>
        <form className="daily-report-filters" onSubmit={applyFilters}>
          <label className="field"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
          <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
          {canViewAll ? <label className="field"><span>User</span><select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}>
            <option value="">All users</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}</select></label> : null}
          <button className="primary-button compact" type="submit">Apply</button></form>
        <div className="daily-report-history">{reports.map((report) => <article className="daily-report-history-item" key={report.id}>
          <div><strong>{displayDate(report.report_date)}</strong><span>{report.user_name}</span></div><pre>{report.report_text}</pre>
          <small>{report.editable ? 'Today' : 'Past date · read-only'}</small></article>)}
          {!loading && !reports.length ? <p>No reports match these filters.</p> : null}</div>
        {reports.length < total ? <button className="secondary-button compact-action" type="button" onClick={() => loadReports(appliedFilters, reports.length).catch((caught) => setError(caught.message))}>Load more</button> : null}
      </section>
    </main>
  </AppLayout>
}

import { useEffect, useMemo, useState } from 'react'
import AppLayout from '../../layouts/app_layout'
import { fetchDailyReports, fetchDailyReportUsers, fetchTodayReport, saveAndCopyTodayReport } from '../../services/dailyReportApi'
import { fetchMainTasks } from '../../services/taskManagementApi'
import { normalizeRole } from '../../utils/roles'
import './dailyReports.css'

const MAX_QUANTITY = 100000
const EMPTY_FILTERS = { date_from: '', date_to: '', user_id: '' }

const SECTIONS = [
  { kind: 'auto', title: 'Automatically counted', hint: 'Pulled from your activity today. Check the numbers and adjust if needed.' },
  { kind: 'manual', title: 'Manual tasks', hint: 'Work that isn’t tracked automatically. Enter what you did.' },
  { kind: 'other', title: 'Other work', hint: 'Anything else you worked on. Enter one remark per line.' },
]

const displayDate = (value) => value ? value.split('-').reverse().join('-') : ''

function longDate(value) {
  if (!value) return ''
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return displayDate(value)
  return parsed.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })
}

const taskKind = (task) => (task.source_type === 'OTHER' ? 'other' : task.source_type === 'MANUAL' ? 'manual' : 'auto')
const toQuantity = (value) => (value === '' || value == null ? NaN : Number(value))
const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?'

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
  const orderedTasks = [...tasks.filter((task) => task.source_type !== 'OTHER'), ...tasks.filter((task) => task.source_type === 'OTHER')]
  orderedTasks.forEach((task) => {
    const quantity = Number(quantities[task.id]?.quantity || 0)
    if (!Number.isInteger(quantity) || quantity <= 0) return
    const remarks = task.source_type === 'OTHER' ? String(quantities[task.id]?.remarks || '').trim() : ''
    if (task.source_type === 'OTHER') {
      lines.push(`${task.name} - ${quantity} :`)
      remarks.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
        .forEach((line, index) => lines.push(`${index + 1}. ${line}`))
    } else {
      lines.push(`${task.name} - ${quantity}`)
    }
  })
  return lines.join('\n').trimEnd()
}

function CopyIcon() {
  return <svg className="dr-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
}

function CheckIcon() {
  return <svg className="dr-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
}

function QuantityStepper({ name, value, onChange }) {
  const numeric = toQuantity(value)
  const current = Number.isFinite(numeric) ? Math.trunc(numeric) : 0
  const step = (delta) => onChange(String(Math.min(MAX_QUANTITY, Math.max(0, current + delta))))
  return <div className="dr-stepper">
    <button type="button" aria-label={`Decrease ${name}`} disabled={current <= 0} onClick={() => step(-1)}>−</button>
    <input type="number" inputMode="numeric" min="0" max={MAX_QUANTITY} step="1" value={value}
      aria-label={`${name} quantity`} onFocus={(event) => event.target.select()} onChange={(event) => onChange(event.target.value)} />
    <button type="button" aria-label={`Increase ${name}`} disabled={current >= MAX_QUANTITY} onClick={() => step(1)}>+</button>
  </div>
}

function TaskRow({ task, entry, onChange }) {
  const quantity = toQuantity(entry?.quantity ?? 0)
  const valid = Number.isInteger(quantity) && quantity >= 0 && quantity <= MAX_QUANTITY
  const hasWork = valid && quantity > 0
  const isOther = task.source_type === 'OTHER'
  const missingRemarks = isOther && hasWork && !String(entry?.remarks || '').trim()
  return <li className={`dr-task${hasWork ? ' is-active' : ''}${valid ? '' : ' is-invalid'}`}>
    <div className="dr-task-info"><span className="dr-task-dot" aria-hidden="true" /><strong>{task.name}</strong></div>
    <QuantityStepper name={task.name} value={entry?.quantity ?? 0} onChange={(value) => onChange('quantity', value)} />
    {isOther && hasWork ? <label className="dr-remarks">
      <span>What did you work on?</span>
      <textarea maxLength="1000" placeholder="Enter each item on a new line" value={entry?.remarks || ''}
        onChange={(event) => onChange('remarks', event.target.value)} />
      <small className={missingRemarks ? 'is-required' : ''}>{missingRemarks ? 'Remarks are required when Other has a quantity.' : `${String(entry?.remarks || '').length}/1000`}</small>
    </label> : null}
  </li>
}

function HistoryCard({ report }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const text = report.report_text || ''
  const long = text.split('\n').length > 7
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { setCopied(false) }
  }
  return <article className="dr-history-card">
    <div className="dr-history-top">
      <span className="dr-avatar small" aria-hidden="true">{initials(report.user_name)}</span>
      <div><strong>{displayDate(report.report_date)}</strong><span>{report.user_name}</span></div>
      <span className={`dr-pill${report.editable ? ' is-today' : ''}`}>{report.editable ? 'Today' : 'Read-only'}</span>
    </div>
    <pre className={`dr-history-text${long && !expanded ? ' is-clamped' : ''}`}>{text}</pre>
    <div className="dr-history-actions">
      {long ? <button type="button" className="dr-link-button" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Show less' : 'Show more'}</button> : <span />}
      <button type="button" className={`dr-link-button${copied ? ' is-done' : ''}`} onClick={copy}>{copied ? <><CheckIcon /> Copied</> : <><CopyIcon /> Copy</>}</button>
    </div>
  </article>
}

export default function DailyReports({ currentUser, onLogout }) {
  const canViewAll = ['ADMIN', 'OPS_MANAGER'].includes(normalizeRole(currentUser?.role))
  const [view, setView] = useState('today')
  const [today, setToday] = useState(null)
  const [mainTasks, setMainTasks] = useState([])
  const [quantities, setQuantities] = useState({})
  const [reports, setReports] = useState([])
  const [total, setTotal] = useState(0)
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const activeTasks = useMemo(() => mainTasks.filter((task) => task.is_active), [mainTasks])
  const reportPreview = today ? previewText(today.report_date, activeTasks, quantities) : ''
  const groupedTasks = useMemo(() => SECTIONS
    .map((section) => ({ ...section, tasks: activeTasks.filter((task) => taskKind(task) === section.kind) }))
    .filter((section) => section.tasks.length), [activeTasks])
  const stats = useMemo(() => {
    let tasksWithWork = 0
    let totalQuantity = 0
    activeTasks.forEach((task) => {
      const quantity = toQuantity(quantities[task.id]?.quantity)
      if (Number.isInteger(quantity) && quantity > 0) { tasksWithWork += 1; totalQuantity += quantity }
    })
    return { tasksWithWork, totalQuantity }
  }, [activeTasks, quantities])
  const hasFilters = Boolean(appliedFilters.date_from || appliedFilters.date_to || appliedFilters.user_id)

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
    if (tasks.some((task) => !Number.isInteger(task.quantity) || task.quantity < 0 || task.quantity > MAX_QUANTITY)) {
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

  async function clearFilters() {
    setError(''); setFilters(EMPTY_FILTERS)
    try { await loadReports(EMPTY_FILTERS); setAppliedFilters(EMPTY_FILTERS) }
    catch (caught) { setError(caught.message) }
  }

  const copyLabel = busy ? 'Saving…' : 'Copy Today’s Stats'

  return <AppLayout activePage="Daily Reports" currentUser={currentUser} onLogout={onLogout}>
    <main className="management-page daily-reports-page">
      <div className="page-header"><div><h1>Daily Reports</h1><p>Review each task quantity before saving your work report.</p></div></div>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {notice ? <p className="form-message success" role="status">{notice}</p> : null}

      <div className="dr-tabs" role="tablist" aria-label="Daily report views">
        <button type="button" role="tab" id="dr-tab-today" aria-selected={view === 'today'} aria-controls="dr-panel-today"
          className={`dr-tab${view === 'today' ? ' is-active' : ''}`} onClick={() => setView('today')}>Today</button>
        <button type="button" role="tab" id="dr-tab-history" aria-selected={view === 'history'} aria-controls="dr-panel-history"
          className={`dr-tab${view === 'history' ? ' is-active' : ''}`} onClick={() => setView('history')}>Saved reports <span className="dr-tab-count">{total}</span></button>
      </div>

      {view === 'today' ? <div className="dr-today" role="tabpanel" id="dr-panel-today" aria-labelledby="dr-tab-today">
        {today ? <>
          <div className="dr-main">
            <div className="dr-summary">
              <div className="dr-stat dr-stat-person">
                <span className="dr-avatar" aria-hidden="true">{initials(today.user_name)}</span>
                <div><small>{longDate(today.report_date)}</small><strong>{today.user_name}</strong></div>
              </div>
              <div className="dr-stat"><small>Tasks with work</small><strong>{stats.tasksWithWork}<span> / {activeTasks.length}</span></strong></div>
              <div className="dr-stat"><small>Total quantity</small><strong>{stats.totalQuantity}</strong></div>
            </div>
            <section className="dr-card" aria-labelledby="dr-tasks-heading">
              <div className="dr-card-head"><div><h2 id="dr-tasks-heading">Task quantities</h2>
                <p>Automatic counts are filled in. Check each one and enter manual work. Set a task to 0 to leave it out.</p></div></div>
              {groupedTasks.map((section) => <div className="dr-group" key={section.kind}>
                <div className="dr-group-head"><span className={`dr-badge dr-badge-${section.kind}`}>{section.title}</span><small>{section.hint}</small></div>
                <ul className="dr-task-list">
                  {section.tasks.map((task) => <TaskRow key={task.id} task={task} entry={quantities[task.id]}
                    onChange={(field, value) => changeTask(task.id, field, value)} />)}
                </ul>
              </div>)}
              {!activeTasks.length ? <p className="dr-empty">No active tasks are configured yet.</p> : null}
            </section>
          </div>

          <aside className="dr-preview" aria-labelledby="dr-preview-heading">
            <div className="dr-preview-head"><h2 id="dr-preview-heading">Work report preview</h2><span className="dr-live">Live</span></div>
            <pre className="dr-preview-text" tabIndex={0} aria-label="Work report preview">
              {stats.tasksWithWork
                ? reportPreview
                : <>{`Work Report: ${displayDate(today.report_date)}\n\n`}<span className="dr-preview-empty">Nothing to report yet. Tasks you add quantities to will appear here.</span></>}
            </pre>
            <button className="primary-button compact" type="button" disabled={busy || !activeTasks.length} onClick={copyToday}>
              <CopyIcon /> {copyLabel}
            </button>
            <p className="dr-hint">This saves today’s quantities, then copies the report to your clipboard. Tasks with a quantity of 0 are left out.</p>
          </aside>
        </> : <section className="dr-card" aria-busy={loading}>
          {loading ? <div className="dr-skeleton" aria-label="Loading today’s report"><span /><span /><span /><span /></div>
            : <p className="dr-empty">Today’s report is unavailable.</p>}
        </section>}
      </div> : <div className="dr-main" role="tabpanel" id="dr-panel-history" aria-labelledby="dr-tab-history">
        <form className="dr-filters" onSubmit={applyFilters}>
          <label className="field"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
          <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
          {canViewAll ? <label className="field"><span>User</span><select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}>
            <option value="">All users</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}</select></label> : null}
          <div className="dr-filters-actions">
            {hasFilters ? <button className="secondary-button compact-action" type="button" onClick={clearFilters}>Clear</button> : null}
            <button className="primary-button compact" type="submit">Apply filters</button>
          </div>
        </form>
        <div className="dr-history-meta"><span>Showing {reports.length} of {total} {total === 1 ? 'report' : 'reports'}{hasFilters ? ' (filtered)' : ''}</span></div>
        {loading ? <div className="dr-skeleton" aria-label="Loading saved reports"><span /><span /><span /></div> : null}
        <div className="dr-history">{reports.map((report) => <HistoryCard key={report.id} report={report} />)}</div>
        {!loading && !reports.length ? <p className="dr-empty">No reports match these filters.</p> : null}
        {reports.length < total ? <button className="secondary-button compact-action dr-load-more" type="button"
          onClick={() => loadReports(appliedFilters, reports.length).catch((caught) => setError(caught.message))}>Load more</button> : null}
      </div>}
    </main>
  </AppLayout>
}

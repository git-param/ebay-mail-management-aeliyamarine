import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { fetchPmsDraft, fetchPmsEntries, savePmsEntry } from '../services/pmsApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

const TASKS = [
  ['sold_posting_score', 'Sold Posting', 'sold_posting'],
  ['m2m_vip_followups_score', 'M2M Queries + VIP Follow-ups', 'm2m_vip_followups'],
  ['tracking_sheet_score', 'Tracking Sheet', 'tracking_sheet'],
  ['purchase_sheet_score', 'Purchase Sheet', 'purchase_sheet'],
  ['booking_score', 'Booking (Invoice + Tracking)', 'booking'],
  ['other_general_work_score', 'Other General Work', 'other_general_work'],
]
const DAY_TYPES = [['WORKING_DAY', 'Working Day'], ['HOLIDAY', 'Holiday'], ['SUNDAY', 'Sunday'], ['LEAVE', 'Leave']]
const FEEDBACK = ['GIVEN', 'PENDING']

function today() {
  return new Date().toISOString().slice(0, 10)
}

function blankEntry(date = today()) {
  return {
    entry_date: date,
    day_type: 'WORKING_DAY',
    sold_posting_score: 0,
    m2m_vip_followups_score: 0,
    tracking_sheet_score: 0,
    purchase_sheet_score: 0,
    booking_score: 0,
    other_general_work_score: 0,
    final_score_percent: 0,
    sla_score: 20,
    feedback_status: 'GIVEN',
    particulars_error_note: 'NA',
    sla_remarks: 'NA',
  }
}

function clampNumber(value) {
  return Math.max(0, Number(value) || 0)
}

function DetailModal({ entry, limits, onClose }) {
  if (!entry) return null
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pms-detail-modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2>{entry.user_name} - {entry.entry_date}</h2>
          <button className="icon-button" type="button" onClick={onClose}>x</button>
        </div>
        <div className="pms-score-grid">
          {TASKS.map(([key, label, limitKey]) => <p key={key}><span>{label}</span><strong>{entry[key]} / {limits[limitKey]}</strong></p>)}
          <p><span>Final Score</span><strong>{entry.final_score_percent}%</strong></p>
          <p><span>SLA Score</span><strong>{entry.sla_score} / 20</strong></p>
          <p><span>Feedback</span><strong>{entry.feedback_status}</strong></p>
          <p><span>Day Type</span><strong>{DAY_TYPES.find(([value]) => value === entry.day_type)?.[1] || entry.day_type}</strong></p>
        </div>
        <section className="drawer-section"><h3>Particulars / Error Note</h3><p>{entry.particulars_error_note || 'NA'}</p></section>
        <section className="drawer-section"><h3>SLA Remarks</h3><p>{entry.sla_remarks || 'NA'}</p></section>
      </section>
    </div>
  )
}

export default function DailyTaskEntry({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role)
  const canViewAll = role === 'ADMIN' || role === 'OPS_MANAGER'
  const [entryDate, setEntryDate] = useState(today())
  const [entry, setEntry] = useState(blankEntry())
  const [limits, setLimits] = useState({ sold_posting: 20, m2m_vip_followups: 25, tracking_sheet: 25, purchase_sheet: 10, booking: 10, other_general_work: 10 })
  const [history, setHistory] = useState({ items: [], total: 0 })
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const totalLimit = useMemo(() => Object.values(limits).reduce((sum, value) => sum + Number(value || 0), 0), [limits])

  async function loadDraft(date = entryDate) {
    try {
      const draft = await fetchPmsDraft({ entry_date: date })
      setLimits(draft.limits)
      setEntry({ ...blankEntry(date), ...draft.entry })
      setError('')
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function loadHistory(next = filters) {
    try {
      const data = await fetchPmsEntries(next)
      setHistory(data)
      setLimits(data.limits || limits)
    } catch (caught) {
      setError(caught.message)
    }
  }

  useEffect(() => { loadDraft(entryDate); loadHistory(filters); if (canViewAll) fetchUsers().then((data) => setUsers(data.items || data || [])).catch(() => setUsers([])) }, [])

  function updateEntry(key, value) {
    setEntry((current) => ({ ...current, [key]: value }))
  }

  function autoSum() {
    const earned = TASKS.reduce((sum, [key, , limitKey]) => sum + Math.min(clampNumber(entry[key]), Number(limits[limitKey] || 0)), 0)
    updateEntry('final_score_percent', totalLimit ? Math.round((earned / totalLimit) * 100) : 0)
  }

  function changeDate(value) {
    setEntryDate(value)
    loadDraft(value)
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await savePmsEntry({ ...entry, entry_date: entryDate })
      setMessage('Daily task entry saved.')
      await loadHistory(filters)
    } catch (caught) {
      setError(caught.message)
    } finally {
      setSaving(false)
    }
  }

  function applyFilters(event) {
    event.preventDefault()
    loadHistory(filters)
  }

  return (
    <AppLayout activePage="Daily Task Entry" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page pms-page">
        <div className="page-header"><div><h1>Daily Task Entry</h1><p>Record PMS task scores and review daily work history</p></div></div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <section className="pms-layout">
          <form className="table-card pms-entry-card" onSubmit={submit}>
            <div className="pms-card-header"><h2>Daily Entry - {currentUser?.full_name || currentUser?.email}</h2></div>
            <div className="pms-form-row">
              <label className="field"><span>Date</span><input type="date" value={entryDate} onChange={(event) => changeDate(event.target.value)} /></label>
              <label className="field"><span>Day Type</span><select value={entry.day_type} onChange={(event) => updateEntry('day_type', event.target.value)}>{DAY_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            </div>
            <section className="pms-task-box">
              <h3>Task Scores</h3>
              {TASKS.map(([key, label, limitKey]) => (
                <label className="pms-task-row" key={key}>
                  <span>{label}</span>
                  <small>/{limits[limitKey]}</small>
                  <input type="text" min="0" value={entry[key]} onChange={(event) => updateEntry(key, clampNumber(event.target.value))} />
                </label>
              ))}
              <label className="pms-task-row final">
                <span>Final Score %</span>
                <button type="button" onClick={autoSum}>Auto-sum</button>
                <input type="text" min="0" value={entry.final_score_percent} onChange={(event) => updateEntry('final_score_percent', clampNumber(event.target.value))} />
              </label>
            </section>
            <div className="pms-form-row">
              <label className="field"><span>SLA Score (0-20)</span><input type="number" min="0" max="20" value={entry.sla_score} onChange={(event) => updateEntry('sla_score', clampNumber(event.target.value))} /></label>
              <label className="field"><span>Feedback Status</span><select value={entry.feedback_status} onChange={(event) => updateEntry('feedback_status', event.target.value)}>{FEEDBACK.map((item) => <option key={item}>{item}</option>)}</select></label>
            </div>
            <label className="field"><span>Particulars / Error Note</span><textarea value={entry.particulars_error_note || ''} onChange={(event) => updateEntry('particulars_error_note', event.target.value)} /></label>
            <label className="field"><span>SLA Remarks</span><textarea value={entry.sla_remarks || ''} onChange={(event) => updateEntry('sla_remarks', event.target.value)} /></label>
            <button className="primary-button compact-action" type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Entry'}</button>
          </form>
          <section className="table-card pms-history-card">
            <div className="pms-card-header"><h2>{canViewAll ? 'Team PMS History' : 'My History'}</h2></div>
            <form className="pms-history-filters" onSubmit={applyFilters}>
              <label className="field"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
              <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
              {canViewAll ? <label className="field"><span>User</span><select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}><option value="">All</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}</select></label> : null}
              <button className="secondary-button compact-action" type="submit">Apply</button>
            </form>
            <div className="table-scroll"><table className="users-table"><thead><tr><th>Date</th>{canViewAll ? <th>User</th> : null}<th>Day</th><th>Final</th><th>SLA</th><th>Feedback</th></tr></thead><tbody>{history.items.map((item) => <tr key={item.id} onClick={() => setSelected(item)}><td>{item.entry_date}</td>{canViewAll ? <td>{item.user_name}</td> : null}<td>{DAY_TYPES.find(([value]) => value === item.day_type)?.[1] || item.day_type}</td><td>{item.final_score_percent}%</td><td>{item.sla_score}/20</td><td>{item.feedback_status}</td></tr>)}</tbody></table></div>
          </section>
        </section>
      </main>
      <DetailModal entry={selected} limits={limits} onClose={() => setSelected(null)} />
    </AppLayout>
  )
}
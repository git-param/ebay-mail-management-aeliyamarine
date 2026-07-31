import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { fetchPmsDraft, fetchPmsEntries, savePmsEntry } from '../services/pmsApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

const DAY_TYPES = [['WORKING_DAY', 'Working Day'], ['HOLIDAY', 'Holiday'], ['SUNDAY', 'Sunday'], ['LEAVE', 'Leave']]
const ERROR_LEVELS = [['NO_ERROR', 'No Error'], ['MINOR', 'Minor'], ['MAJOR', 'Major']]
const FEEDBACK = ['GIVEN', 'PENDING']
const today = () => new Date().toISOString().slice(0, 10)

function blankEntry(date = today()) {
  return { entry_date: date, day_type: 'WORKING_DAY', score_items: [], final_score_percent: 0, sla_score: 0, error_level: 'NO_ERROR', error_remark: '', feedback_status: 'GIVEN', particulars_error_note: 'NA', sla_remarks: 'NA' }
}

function number(value) {
  return Math.max(0, Number(value) || 0)
}

function calculate(items, slaScore, errorLevel) {
  if (errorLevel === 'MAJOR') return 0
  const applicable = (items || []).filter((item) => item.status !== 'NOT_APPLICABLE' && (item.status === 'ENTERED' || number(item.value) > 0))
  const earned = applicable.reduce((sum, item) => sum + Math.min(number(item.value), number(item.max_score) || 1), 0) + Math.min(number(slaScore), 20)
  const possible = applicable.reduce((sum, item) => sum + (number(item.max_score) || 1), 0) + 20
  return possible ? Math.round((earned / possible) * 100) : 0
}

function sourceLabel(source) {
  return source === 'AUTO' ? 'Fetched' : 'Manual'
}

function DetailModal({ entry, onClose }) {
  if (!entry) return null
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pms-detail-modal" role="dialog" aria-modal="true">
        <div className="modal-header"><h2>{entry.user_name} - {entry.entry_date}</h2><button className="icon-button" type="button" onClick={onClose}>x</button></div>
        <div className="pms-score-grid">
          {(entry.score_items || []).map((item) => <p key={item.key}><span>{item.label}</span><strong>{item.status === 'NOT_APPLICABLE' ? 'N/A' : `${item.value} / ${item.max_score}`}</strong></p>)}
          <p><span>SLA Score</span><strong>{entry.sla_score}/20</strong></p>
          <p><span>Final Score</span><strong>{entry.final_score_percent}%</strong></p>
          <p><span>Error</span><strong>{ERROR_LEVELS.find(([value]) => value === entry.error_level)?.[1] || entry.error_level}</strong></p>
          <p><span>Feedback</span><strong>{entry.feedback_status}</strong></p>
        </div>
        {entry.error_remark ? <section className="drawer-section"><h3>Error Remark</h3><p>{entry.error_remark}</p></section> : null}
        <section className="drawer-section"><h3>Particulars / Error Note</h3><p>{entry.particulars_error_note || 'NA'}</p></section>
        <section className="drawer-section"><h3>SLA Remarks</h3><p>{entry.sla_remarks || 'NA'}</p></section>
        <section className="drawer-section"><h3>Audit</h3><p>Created by {entry.created_by_name || '-'} - Updated by {entry.updated_by_name || '-'}</p></section>
      </section>
    </div>
  )
}

export default function DailyTaskEntry({ currentUser, onLogout }) {
  const isAdmin = normalizeRole(currentUser?.role) === 'ADMIN'
  const [users, setUsers] = useState([])
  const [selectedUserId, setSelectedUserId] = useState('')
  const [entryDate, setEntryDate] = useState(today())
  const [entry, setEntry] = useState(blankEntry())
  const [history, setHistory] = useState({ items: [], total: 0 })
  const [filters, setFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const selectedUser = useMemo(() => users.find((user) => user.id === selectedUserId), [users, selectedUserId])

  async function loadHistory(next = filters) {
    try {
      setHistory(await fetchPmsEntries(next))
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function loadDraft(userId = selectedUserId, date = entryDate) {
    if (!isAdmin || !userId || !date) return
    try {
      const draft = await fetchPmsDraft({ user_id: userId, entry_date: date })
      setEntry({ ...blankEntry(date), ...draft.entry, final_score_percent: draft.entry.final_score_percent || 0 })
      setError('')
    } catch (caught) {
      setError(caught.message)
    }
  }

  useEffect(() => {
    loadHistory(filters)
    if (isAdmin) fetchUsers().then((data) => setUsers(data.items || data || [])).catch(() => setUsers([]))
  }, [])

  function updateItem(key, patch) {
    setEntry((current) => {
      const nextItems = current.score_items.map((item) => item.key === key ? { ...item, ...patch, source: patch.source || item.source } : item)
      return { ...current, score_items: current.error_level === 'MAJOR' ? nextItems.map((item) => ({ ...item, value: 0 })) : nextItems }
    })
  }

  function updateEntry(key, value) {
    setEntry((current) => {
      const next = { ...current, [key]: value }
      if (key === 'error_level' && value === 'MAJOR') {
        next.score_items = current.score_items.map((item) => ({ ...item, value: 0, status: item.status === 'NOT_APPLICABLE' ? item.status : 'ENTERED' }))
        next.sla_score = 0
        next.final_score_percent = 0
      }
      if (key === 'error_level' && value === 'NO_ERROR') next.error_remark = ''
      return next
    })
  }

  function autoSum() {
    setEntry((current) => ({ ...current, final_score_percent: calculate(current.score_items, current.sla_score, current.error_level) }))
  }

  async function submit(event) {
    event.preventDefault()
    if (!isAdmin) return
    if (!selectedUserId) { setError('Select a user before saving.'); return }
    if (entry.error_level !== 'NO_ERROR' && !entry.error_remark.trim()) { setError('Error Remark is required for Minor or Major errors.'); return }
    setSaving(true); setError(''); setMessage('')
    try {
      const payload = { ...entry, user_id: selectedUserId, entry_date: entryDate, final_score_percent: calculate(entry.score_items, entry.sla_score, entry.error_level) }
      const saved = await savePmsEntry(payload)
      setEntry(saved)
      setMessage('Daily entry saved.')
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
        <div className="page-header"><div><h1>Daily Task Entry</h1><p>{isAdmin ? 'Create and review PMS entries for the team' : 'View your Daily Entry scores and history'}</p></div></div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <section className="pms-layout">
          {isAdmin ? (
            <form className="table-card pms-entry-card" onSubmit={submit}>
              <div className="pms-card-header"><h2>Admin Daily Entry</h2></div>
              <div className="pms-form-row">
                <label className="field"><span>User</span><select value={selectedUserId} onChange={(event) => { setSelectedUserId(event.target.value); loadDraft(event.target.value, entryDate) }}><option value="">Select user</option>{users.map((user) => <option value={user.id} key={user.id}>{user.full_name || user.email}</option>)}</select></label>
                <label className="field"><span>Date</span><input type="date" value={entryDate} onChange={(event) => { setEntryDate(event.target.value); loadDraft(selectedUserId, event.target.value) }} /></label>
              </div>
              <section className="pms-task-box">
                <h3>Task Scores {selectedUser ? `- ${selectedUser.full_name || selectedUser.email}` : ''}</h3>
                {(entry.score_items || []).map((item) => (
                  <div className="pms-dynamic-row" key={item.key}>
                    <div><strong>{item.label}</strong><small>{sourceLabel(item.source)}</small></div>
                    <select value={item.status} disabled={entry.error_level === 'MAJOR'} onChange={(event) => updateItem(item.key, { status: event.target.value, source: 'MANUAL' })}><option value="NOT_ENTERED">Not Entered</option><option value="ENTERED">Entered</option><option value="NOT_APPLICABLE">Not Applicable</option></select>
                    <span>/{item.max_score}</span>
                    <input type="number" min="0" max={item.max_score} disabled={entry.error_level === 'MAJOR' || item.status === 'NOT_APPLICABLE'} value={entry.error_level === 'MAJOR' ? 0 : item.value} onChange={(event) => updateItem(item.key, { value: number(event.target.value), status: 'ENTERED', source: 'MANUAL' })} />
                  </div>
                ))}
                <div className="pms-dynamic-row">
                  <div><strong>SLA Score</strong><small>Fetched</small></div><span /><span>/20</span>
                  <input type="number" min="0" max="20" disabled={entry.error_level === 'MAJOR'} value={entry.error_level === 'MAJOR' ? 0 : entry.sla_score} onChange={(event) => updateEntry('sla_score', number(event.target.value))} />
                </div>
                <label className="pms-task-row final"><span>Final Score %</span><button type="button" onClick={autoSum}>Auto Sum</button><input type="number" min="0" max="100" value={entry.final_score_percent} onChange={(event) => updateEntry('final_score_percent', number(event.target.value))} /></label>
              </section>
              <div className="pms-form-row">
                <label className="field"><span>Day Type</span><select value={entry.day_type} onChange={(event) => updateEntry('day_type', event.target.value)}>{DAY_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="field"><span>Error</span><select value={entry.error_level} onChange={(event) => updateEntry('error_level', event.target.value)}>{ERROR_LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              </div>
              {entry.error_level !== 'NO_ERROR' ? <label className="field"><span>Error Remark</span><textarea required value={entry.error_remark || ''} onChange={(event) => updateEntry('error_remark', event.target.value)} /></label> : null}
              <label className="field"><span>Feedback Status</span><select value={entry.feedback_status} onChange={(event) => updateEntry('feedback_status', event.target.value)}>{FEEDBACK.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label className="field"><span>Particulars / Error Note</span><textarea value={entry.particulars_error_note || ''} onChange={(event) => updateEntry('particulars_error_note', event.target.value)} /></label>
              <label className="field"><span>SLA Remarks</span><textarea value={entry.sla_remarks || ''} onChange={(event) => updateEntry('sla_remarks', event.target.value)} /></label>
              <button className="primary-button compact-action" type="submit" disabled={saving || !selectedUserId}>{saving ? 'Saving...' : 'Save Entry'}</button>
            </form>
          ) : null}
          <section className="table-card pms-history-card">
            <div className="pms-card-header"><h2>{isAdmin ? 'Team PMS History' : 'My History'}</h2></div>
            <form className="pms-history-filters" onSubmit={applyFilters}>
              <label className="field"><span>From</span><input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} /></label>
              <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
              {isAdmin ? <label className="field"><span>User</span><select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}><option value="">All</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}</select></label> : null}
              <button className="secondary-button compact-action" type="submit">Apply</button>
            </form>
            <div className="table-scroll"><table className="users-table"><thead><tr><th>Date</th>{isAdmin ? <th>User</th> : null}<th>Day</th><th>Final</th><th>SLA</th><th>Error</th></tr></thead><tbody>{history.items.map((item) => <tr key={item.id} onClick={() => setSelected(item)}><td>{item.entry_date}</td>{isAdmin ? <td>{item.user_name}</td> : null}<td>{DAY_TYPES.find(([value]) => value === item.day_type)?.[1] || item.day_type}</td><td>{item.final_score_percent}%</td><td>{item.sla_score}/20</td><td>{ERROR_LEVELS.find(([value]) => value === item.error_level)?.[1] || item.error_level}</td></tr>)}</tbody></table></div>
          </section>
        </section>
      </main>
      <DetailModal entry={selected} onClose={() => setSelected(null)} />
    </AppLayout>
  )
}

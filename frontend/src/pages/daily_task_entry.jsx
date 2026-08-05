import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { fetchPmsEntries, loadPmsDailyEntries, uploadPmsDailyEntries } from '../services/pmsApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

const DAY_TYPES = [['WORKING_DAY', 'Working Day'], ['HOLIDAY', 'Holiday'], ['SUNDAY', 'Sunday'], ['LEAVE', 'Leave']]
const ERROR_LEVELS = [['NO_ERROR', 'None'], ['MINOR', 'Minor'], ['MAJOR', 'Major']]
const SLA_MAX = 20
const today = () => new Date().toISOString().slice(0, 10)

function number(value) {
  return Math.max(0, Number(value) || 0)
}

function clamp(value, max) {
  return Math.min(Math.max(0, number(value)), max)
}

function calculate(items, slaScore, errorLevel) {
  if (errorLevel === 'MAJOR') return 0
  const applicable = (items || []).filter((item) => item.status !== 'NOT_APPLICABLE')
  const earned = applicable.reduce((sum, item) => sum + Math.min(number(item.value), number(item.max_score) || 1), 0) + Math.min(number(slaScore), SLA_MAX)
  const possible = applicable.reduce((sum, item) => sum + (number(item.max_score) || 1), 0) + SLA_MAX
  return possible ? Math.round((earned / possible) * 100) : 0
}

function sourceLabel(source) {
  return source === 'AUTO' ? 'Auto Fetched' : 'Manual Entry'
}

function makeRow(loadedItem) {
  const entry = loadedItem.entry
  return {
    userId: loadedItem.user.id,
    userName: loadedItem.user.full_name || loadedItem.user.email,
    userEmail: loadedItem.user.email,
    existingEntryId: loadedItem.existing_entry_id,
    selected: !loadedItem.existing_entry_id,
    entry_date: entry.entry_date,
    day_type: entry.day_type,
    score_items: entry.score_items || [],
    sla_score: entry.sla_score || 0,
    error_level: entry.error_level,
    error_remark: entry.error_remark || '',
    remarks: entry.remarks || '',
    particulars_error_note: entry.particulars_error_note || '',
    sla_remarks: entry.sla_remarks || '',
    final_score_percent: entry.final_score_percent || 0,
    // Already-saved entries (existing_entry_id present) load locked/read-only.
    // Admin must click Unlock to Edit to change and re-upload.
    status: loadedItem.existing_entry_id ? 'success' : 'idle', // idle | success | error
    statusMessage: '',
    // snapshot kept so we can restore suggested scores if Major is toggled off again
    _preErrorItems: entry.score_items || [],
    _preErrorSla: entry.sla_score || 0,
  }
}

function DetailModal({ entry, onClose }) {
  if (!entry) return null
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel pms-detail-modal" role="dialog" aria-modal="true">
        <div className="modal-header"><h2>{entry.user_name} - {entry.entry_date}</h2><button className="icon-button" type="button" onClick={onClose}>x</button></div>
        <div className="pms-score-grid">
          {(entry.score_items || []).map((item) => <p key={item.key}><span>{item.label}</span><strong>{item.status === 'NOT_APPLICABLE' ? 'N/A' : `${item.value} / ${item.max_score}`}</strong></p>)}
          <p><span>SLA Score</span><strong>{entry.sla_score}/{SLA_MAX}</strong></p>
          <p><span>Final Score</span><strong>{entry.final_score_percent}%</strong></p>
          <p><span>Error</span><strong>{ERROR_LEVELS.find(([value]) => value === entry.error_level)?.[1] || entry.error_level}</strong></p>
        </div>
        {entry.error_remark ? <section className="drawer-section"><h3>Error Remark</h3><p>{entry.error_remark}</p></section> : null}
        {entry.remarks ? <section className="drawer-section"><h3>Remarks</h3><p>{entry.remarks}</p></section> : null}
        <section className="drawer-section"><h3>Particulars / Error Note</h3><p>{entry.particulars_error_note || 'NA'}</p></section>
        <section className="drawer-section"><h3>SLA Remarks</h3><p>{entry.sla_remarks || 'NA'}</p></section>
        <section className="drawer-section"><h3>Audit</h3><p>Created by {entry.created_by_name || '-'} - Updated by {entry.updated_by_name || '-'}</p></section>
      </section>
    </div>
  )
}

function AgentCard({ row, onChange }) {
  const totalTaskEarned = (row.score_items || []).filter((item) => item.status !== 'NOT_APPLICABLE').reduce((sum, item) => sum + number(item.value), 0)
  const totalTaskMax = (row.score_items || []).filter((item) => item.status !== 'NOT_APPLICABLE').reduce((sum, item) => sum + number(item.max_score), 0)
  const isMajor = row.error_level === 'MAJOR'
  const isLocked = row.status === 'success'
  const isDisabled = isLocked || isMajor

  function patch(fields) {
    if (isLocked) return
    onChange(row.userId, (current) => {
      const next = { ...current, ...fields }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level)
      return next
    })
  }

  function updateItem(key, patchFields) {
    if (isLocked) return
    onChange(row.userId, (current) => {
      const nextItems = current.score_items.map((item) => item.key === key ? { ...item, ...patchFields, source: patchFields.value !== undefined ? 'MANUAL' : item.source } : item)
      const next = { ...current, score_items: nextItems }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level)
      return next
    })
  }

  function updateErrorLevel(value) {
    if (isLocked) return
    onChange(row.userId, (current) => {
      if (value === 'MAJOR') {
        const zeroedItems = current.score_items.map((item) => ({ ...item, value: 0 }))
        return {
          ...current,
          error_level: value,
          _preErrorItems: current.error_level === 'MAJOR' ? current._preErrorItems : current.score_items,
          _preErrorSla: current.error_level === 'MAJOR' ? current._preErrorSla : current.sla_score,
          score_items: zeroedItems,
          sla_score: 0,
          final_score_percent: 0,
        }
      }
      const restoredItems = current.error_level === 'MAJOR' ? current._preErrorItems : current.score_items
      const restoredSla = current.error_level === 'MAJOR' ? current._preErrorSla : current.sla_score
      const next = {
        ...current,
        error_level: value,
        score_items: restoredItems,
        sla_score: restoredSla,
        error_remark: value === 'NO_ERROR' ? '' : current.error_remark,
      }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level)
      return next
    })
  }

  return (
    <section className={`table-card pms-agent-card${isLocked ? ' locked' : ''}`}>
      <div className="pms-card-header pms-agent-card-header">
        <label className="checkbox-field"><input type="checkbox" checked={row.selected} onChange={(event) => onChange(row.userId, (current) => ({ ...current, selected: event.target.checked }))} /></label>
        <div><h3>{row.userName}</h3><small>{row.userEmail}</small></div>
        {isLocked ? <span className="upload-status success">Uploaded &amp; Locked</span> : null}
        {row.status === 'error' ? <span className="upload-status error">{row.statusMessage || 'Failed'}</span> : null}
        {isLocked ? <button className="unlock-button" type="button" onClick={() => onChange(row.userId, (current) => ({ ...current, status: 'idle', statusMessage: '' }))}>Unlock to Edit</button> : null}
      </div>
      {isLocked ? <p className="field-help locked-help">This entry has been uploaded and is locked from editing. Click "Unlock to Edit" to make changes and re-upload.</p> : null}

      <section className="pms-task-box">
        {(row.score_items || []).length === 0 ? <p className="field-help">No subtasks assigned to this agent.</p> : null}
        {(row.score_items || []).map((item) => (
          <div className="pms-dynamic-row" key={item.key}>
            <div>
              <strong>{item.label}</strong>
              <small>{sourceLabel(item.source)}{item.source === 'AUTO' ? ` \u00b7 Activity: ${item.activity_count ?? 0}` : ''}</small>
            </div>
            <span>/{item.max_score}</span>
            <input
              type="number"
              min="0"
              max={item.max_score}
              disabled={isDisabled || item.status === 'NOT_APPLICABLE'}
              value={isMajor ? 0 : item.value}
              onChange={(event) => updateItem(item.key, { value: clamp(event.target.value, item.max_score), status: 'ENTERED' })}
            />
          </div>
        ))}
        <div className="pms-dynamic-row">
          <div><strong>SLA Score</strong><small>Manual</small></div>
          <span>/{SLA_MAX}</span>
          <input type="number" min="0" max={SLA_MAX} disabled={isDisabled} value={isMajor ? 0 : row.sla_score} onChange={(event) => patch({ sla_score: clamp(event.target.value, SLA_MAX) })} />
        </div>
        <div className="pms-task-row final">
          <span>Task Total</span><strong>{isMajor ? 0 : totalTaskEarned}/{totalTaskMax}</strong>
          <span>Final Score</span><strong>{row.final_score_percent}%</strong>
        </div>
      </section>

      <div className="pms-form-row">
        <label className="field"><span>Day Type</span><select disabled={isLocked} value={row.day_type} onChange={(event) => patch({ day_type: event.target.value })}>{DAY_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field"><span>Error</span><select disabled={isLocked} value={row.error_level} onChange={(event) => updateErrorLevel(event.target.value)}>{ERROR_LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {row.error_level !== 'NO_ERROR' ? <label className="field">
        <span>Error Remarks (required)</span>
        <textarea disabled={isLocked} required value={row.error_remark} onChange={(event) => patch({ error_remark: event.target.value })} />
      </label> : null}
      <label className="field">
        <span>Remarks</span><textarea disabled={isLocked} value={row.remarks} onChange={(event) => patch({ remarks: event.target.value })} placeholder="General feedback or notes for this agent and date" />
      </label>
      <label className="field">
        <span>Particulars / Error Note</span><textarea disabled={isLocked} value={row.particulars_error_note} onChange={(event) => patch({ particulars_error_note: event.target.value })} />
      </label>
      <label className="field">
        <span>SLA Remarks</span><textarea disabled={isLocked} value={row.sla_remarks} onChange={(event) => patch({ sla_remarks: event.target.value })} />
      </label>
    </section>
  )
}

export default function DailyTaskEntry({ currentUser, onLogout }) {
  const isAdmin = normalizeRole(currentUser?.role) === 'ADMIN'
  const [users, setUsers] = useState([])
  const [entryDate, setEntryDate] = useState(today())
  const [agentFilter, setAgentFilter] = useState('')
  const [rows, setRows] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [history, setHistory] = useState({ items: [], total: 0 })
  const [filters, setFilters] = useState({ date_from: '', date_to: '', user_id: '' })
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const eligibleRows = useMemo(() => rows.filter((row) => row.status !== 'success'), [rows])
  const selectedCount = useMemo(() => eligibleRows.filter((row) => row.selected).length, [eligibleRows])
  const lockedCount = rows.length - eligibleRows.length

  async function loadHistory(next = filters) {
    try {
      setHistory(await fetchPmsEntries(next))
    } catch (caught) {
      setError(caught.message)
    }
  }

  useEffect(() => {
    loadHistory(filters)
    if (isAdmin) fetchUsers().then((data) => setUsers(data.items || data || [])).catch(() => setUsers([]))
  }, [])

  async function loadDailyEntries() {
    if (!isAdmin || !entryDate) return
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const response = await loadPmsDailyEntries({ entry_date: entryDate, user_id: agentFilter || undefined })
      setRows((response.items || []).map(makeRow))
      setLoaded(true)
    } catch (caught) {
      setError(caught.message)
    } finally {
      setLoading(false)
    }
  }

  function updateRow(userId, updater) {
    setRows((current) => current.map((row) => (row.userId === userId ? updater(row) : row)))
  }

  function selectAll(value) {
    setRows((current) => current.map((row) => (row.status === 'success' ? row : { ...row, selected: value })))
  }

  async function upload(scope) {
    const eligible = rows.filter((row) => row.status !== 'success')
    const targets = scope === 'selected' ? eligible.filter((row) => row.selected) : eligible
    if (!targets.length) {
      setError(rows.length && !eligible.length ? 'All loaded entries are already uploaded and locked.' : 'No agent rows to upload.')
      return
    }
    const missingRemark = targets.find((row) => row.error_level !== 'NO_ERROR' && !row.error_remark.trim())
    if (missingRemark) {
      setError(`Error Remarks is required for ${missingRemark.userName} (Minor/Major error selected).`)
      return
    }
    setUploading(true)
    setError('')
    setMessage('')
    try {
      const entries = targets.map((row) => ({
        user_id: row.userId,
        entry_date: row.entry_date,
        day_type: row.day_type,
        score_items: row.score_items,
        sla_score: row.sla_score,
        error_level: row.error_level,
        error_remark: row.error_remark || null,
        remarks: row.remarks || null,
        particulars_error_note: row.particulars_error_note || null,
        sla_remarks: row.sla_remarks || null,
        final_score_percent: row.final_score_percent,
      }))
      const response = await uploadPmsDailyEntries(entries)
      const resultByUser = new Map((response.results || []).map((item) => [item.user_id, item]))
      setRows((current) => current.map((row) => {
        const result = resultByUser.get(row.userId)
        if (!result) return row
        return { ...row, status: result.success ? 'success' : 'error', statusMessage: result.success ? '' : result.error }
      }))
      const failCount = (response.results || []).filter((item) => !item.success).length
      const successCount = (response.results || []).filter((item) => item.success).length
      if (failCount) setError(`${failCount} of ${response.results.length} entries failed to upload. Check the flagged agent cards below.`)
      else setMessage(`${successCount} daily entr${successCount === 1 ? 'y' : 'ies'} uploaded successfully.`)
      await loadHistory(filters)
    } catch (caught) {
      setError(caught.message)
    } finally {
      setUploading(false)
    }
  }

  function applyFilters(event) {
    event.preventDefault()
    loadHistory(filters)
  }

  return (
    <AppLayout activePage="Daily Task Entry" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page pms-page">
        <div className="page-header"><div><h1>Daily Task Entry</h1><p>{isAdmin ? 'Load, review and upload PMS entries for the team' : 'View your Daily Entry scores and history'}</p></div></div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <section className="pms-daily-entry-layout">
          {isAdmin ? (
            <section className="table-card pms-load-card">
              <div className="pms-card-header"><h2>Load Daily Entries</h2></div>
              <p className="field-help">Only Agent-role users are loaded here. Operations Managers and Admins are not included.</p>
              <div className="pms-form-row pms-load-controls">
                <label className="field"><span>Date</span><input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} /></label>
                <button className="primary-button compact-action" type="button" onClick={loadDailyEntries} disabled={loading}>{loading ? 'Loading...' : 'Load Daily Entries'}</button>
              </div>

              {loaded ? (
                <>
                  <div className="pms-bulk-actions">
                    <button className="secondary-button compact-action" type="button" onClick={() => selectAll(true)}>Select All</button>
                    <button className="secondary-button compact-action" type="button" onClick={() => selectAll(false)}>Deselect All</button>
                    <span className="field-help">{selectedCount} of {eligibleRows.length} selected{lockedCount ? ` \u00b7 ${lockedCount} already uploaded` : ''}</span>
                    <span className="pms-bulk-actions-spacer" />
                    <button className="primary-button compact-action" type="button" onClick={() => upload('selected')} disabled={uploading || !selectedCount}>{uploading ? 'Uploading...' : 'Upload Selected Entries'}</button>
                    <button className="primary-button compact-action" type="button" onClick={() => upload('all')} disabled={uploading || !eligibleRows.length}>{uploading ? 'Uploading...' : 'Upload All Loaded Entries'}</button>
                  </div>
                  {rows.length === 0 ? <p className="field-help">No active agents found for this selection.</p> : null}
                  <div className="pms-agent-cards">
                    {rows.map((row) => <AgentCard key={row.userId} row={row} onChange={updateRow} />)}
                  </div>
                </>
              ) : null}
            </section>
          ) : null}
          <section className="table-card pms-history-card">
            <div className="pms-card-header"><h2>{isAdmin ? 'Team PMS History' : 'My History'}</h2></div>
            <form className="pms-history-filters" onSubmit={applyFilters}>
              <label className="field">
                <span>From</span>
                <input type="date" value={filters.date_from} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value }))} />
              </label>
              <label className="field"><span>To</span><input type="date" value={filters.date_to} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value }))} /></label>
              {isAdmin ? <label className="field"><span>User</span><select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}><option value="">All</option>{users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}</select></label> : null}
              <button className="secondary-button compact-action" type="submit">Apply</button>
            </form>
            <div className="table-scroll">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    {isAdmin ? <th>User</th> : null}
                    <th>Day</th>
                    <th>Final</th>
                    <th>SLA</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {history.items.map((item) => <tr key={item.id} onClick={() => setSelected(item)}>
                    <td>{item.entry_date}</td>
                    {isAdmin ? <td>{item.user_name}</td> : null}
                    <td>{DAY_TYPES.find(([value]) => value === item.day_type)?.[1] || item.day_type}</td>
                    <td>{item.final_score_percent}%</td>
                    <td>{item.sla_score}/{SLA_MAX}</td>
                    <td>{ERROR_LEVELS.find(([value]) => value === item.error_level)?.[1] || item.error_level}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      </main>
      <DetailModal entry={selected} onClose={() => setSelected(null)} />
    </AppLayout>
  )
}
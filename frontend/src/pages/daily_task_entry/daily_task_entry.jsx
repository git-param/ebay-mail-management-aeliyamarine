import { useEffect, useMemo, useRef, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import {
  fetchDailyEntries,
  fetchDailyEntrySlaReview,
  loadDailyEntries as apiLoadDailyEntries,
  uploadDailyEntries,
} from '../../services/dailyEntryApi'
import { fetchUsers } from '../../services/userApi'
import { normalizeRole } from '../../utils/roles'

import './daily_task_entry.css'

const DAY_TYPES = [['WORKING_DAY', 'Working Day'], ['HOLIDAY', 'Holiday'], ['SUNDAY', 'Sunday'], ['LEAVE', 'Leave']]
const ERROR_LEVELS = [['NO_ERROR', 'None'], ['MINOR', 'Minor'], ['MAJOR', 'Major']]
const SLA_MAX = 20
const OTHER_GENERAL_WORK_KEY = 'other_general_work'
const today = () => new Date().toISOString().slice(0, 10)

function number(value) {
  return Math.max(0, Number(value) || 0)
}

function clamp(value, max) {
  return Math.min(Math.max(0, number(value)), max)
}

function taskPerformancePercent(item) {
  const maxScore = Math.max(1, number(item?.max_score) || 1)
  return (Math.min(number(item?.value), maxScore) / maxScore) * 100
}

function taskAveragePercent(items) {
  const applicable = (items || []).filter((item) => item.status === 'ENTERED')
  if (!applicable.length) return 0
  return applicable.reduce((sum, item) => sum + taskPerformancePercent(item), 0) / applicable.length
}

function effectiveSlaScore(slaScore, slaTotalCount) {
  return number(slaTotalCount) === 0 ? SLA_MAX : Math.min(number(slaScore), SLA_MAX)
}

function slaPerformancePercent(slaScore, slaTotalCount) {
  return (effectiveSlaScore(slaScore, slaTotalCount) / SLA_MAX) * 100
}

function formatPercent(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatScore(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function parentTaskLabel(label) {
  const parts = String(label || '').split(' - ')
  if (parts.length > 2) return parts[parts.length - 2]
  return parts.length > 1 ? parts[parts.length - 1] : label
}

function childTaskLabel(label) {
  const parts = String(label || '').split(' - ')
  return parts.length > 2 ? parts[parts.length - 1] : label
}

function buildTaskDisplayItems(items) {
  const groups = new Map()
  const displayItems = []

  for (const item of items || []) {
    if (!item.sub_subtask_id) {
      displayItems.push({ ...item, display_key: item.key, label: parentTaskLabel(item.label), child_items: [] })
      continue
    }

    const groupKey = item.subtask_id || item.key
    if (!groups.has(groupKey)) {
      const group = {
        ...item,
        key: `subtask:${groupKey}`,
        display_key: `subtask:${groupKey}`,
        label: parentTaskLabel(item.label),
        value: 0,
        max_score: 0,
        status: 'NOT_APPLICABLE',
        activity_count: 0,
        child_items: [],
      }
      groups.set(groupKey, group)
      displayItems.push(group)
    }

    const group = groups.get(groupKey)
    group.child_items.push(item)
    group.value += number(item.value)
    group.max_score += number(item.max_score)
    group.activity_count += number(item.activity_count)
    if (item.status === 'ENTERED') group.status = 'ENTERED'
    if (item.source === 'AUTO') group.source = 'AUTO'
  }

  return displayItems
}

function calculate(items, slaScore, errorLevel, slaTotalCount = null) {
  if (errorLevel === 'MAJOR') return 0
  const taskAverage = taskAveragePercent(items)
  const slaPerformance = slaPerformancePercent(slaScore, slaTotalCount)
  return Math.round(Math.min(100, Math.max(0, (taskAverage + slaPerformance) / 2)))
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
    sla_met_count: entry.sla_met_count,
    sla_total_count: entry.sla_total_count,
    sla_auto_fetched: entry.sla_auto_fetched || false,
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
  const displayItems = buildTaskDisplayItems(entry.score_items)
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel dailyEntry-detail-modal" role="dialog" aria-modal="true">
        <div className="modal-header"><h2>{entry.user_name} - {entry.entry_date}</h2><button className="icon-button" type="button" onClick={onClose}>x</button></div>
        <div className="dailyEntry-score-grid">
          {displayItems.map((item) => <p key={item.key}><span>{item.label}</span><strong>{item.status === 'ENTERED' ? `${formatScore(item.value)} / ${formatScore(item.max_score)}` : 'N/A'}</strong></p>)}
          <p><span>SLA Score</span><strong>{entry.sla_score}/{SLA_MAX}</strong></p>
          <p><span>Final Score</span><strong>{entry.final_score_percent}%</strong></p>
          <p><span>Error</span><strong>{ERROR_LEVELS.find(([value]) => value === entry.error_level)?.[1] || entry.error_level}</strong></p>
        </div>
        {entry.error_remark ? <section className="drawer-section"><h3>Error Remark</h3><p>{entry.error_remark}</p></section> : null}
        {entry.remarks ? <section className="drawer-section"><h3>Remarks</h3><p>{entry.remarks}</p></section> : null}
        <section className="drawer-section">
          <h3>Particulars / Error Note</h3>
          <p>{entry.particulars_error_note || 'NA'}</p>
        </section>
        <section className="drawer-section">
          <h3>SLA Remarks</h3>
          <p>{entry.sla_remarks || 'NA'}</p>
        </section>
        <section className="drawer-section">
          <h3>Audit</h3>
          <p>Created by {entry.created_by_name || '-'} - Updated by {entry.updated_by_name || '-'}</p>
        </section>
      </section>
    </div>
  )
}

// Small click-to-open popover showing the fetched Other General Work breakdown,
// e.g. "Sold Posting - 3", "Offer Management - 2". Rows sourced from individual
// conversations (currently Message Type activity) list each conversation as a
// link so an admin can jump straight to it, even when no SLA cycle exists.
function OtherGeneralWorkInfo({ breakdown }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const items = breakdown || []

  useEffect(() => {
    if (!open) return undefined
    function handleOutsideClick(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [open])

  return (
    <span className="dailyEntry-info-popover-wrap" ref={wrapRef}>
      <button
        type="button"
        className="dailyEntry-info-trigger"
        aria-label="Show Other General Work breakdown"
        onClick={() => setOpen((current) => !current)}
      >
        i
      </button>
      {open ? (
        <div className="dailyEntry-info-popover" role="tooltip">
          {items.length === 0 ? (
            <p className="dailyEntry-info-popover-empty">No unassigned activity found for this date.</p>
          ) : (
            <ul>
              {items.map((entry) => (
                <li key={entry.label}>
                  <div className="dailyEntry-info-popover-row">
                    <span>{entry.label}</span>
                    <strong>{entry.count}</strong>
                  </div>
                  {(entry.conversation_ids || []).length > 0 ? (
                    <ul className="dailyEntry-info-popover-links">
                      {entry.conversation_ids.map((conversationId, index) => (
                        <li key={conversationId}>
                          <a href={`/inbox?conversation_id=${encodeURIComponent(conversationId)}`} target="_blank" rel="noreferrer">
                            Conversation {index + 1}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </span>
  )
}

function SubtaskChildrenInfo({ children }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const items = children || []

  useEffect(() => {
    if (!open) return undefined
    function handleOutsideClick(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [open])

  if (!items.length) return null

  return (
    <span className="dailyEntry-info-popover-wrap" ref={wrapRef}>
      <button
        type="button"
        className="dailyEntry-info-trigger"
        aria-label="Show sub-subtask breakdown"
        onClick={() => setOpen((current) => !current)}
      >
        i
      </button>
      {open ? (
        <div className="dailyEntry-info-popover" role="tooltip">
          <ul>
            {items.map((item) => (
              <li key={item.key}>
                <div className="dailyEntry-info-popover-row">
                  <span>{childTaskLabel(item.label)}</span>
                  <strong>{item.activity_count ?? 0} handled</strong>
                </div>
                <p className="dailyEntry-info-popover-empty">{formatScore(item.value)} / {formatScore(item.max_score)}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </span>
  )
}

function SlaReviewModal({ userId, userName, entryDate, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    fetchDailyEntrySlaReview({ user_id: userId, entry_date: entryDate })
      .then((response) => { if (!cancelled) setData(response) })
      .catch((caught) => { if (!cancelled) setError(caught.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userId, entryDate])

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '-'
    const minutes = Math.floor(seconds / 60)
    const remaining = seconds % 60
    return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel dailyEntry-sla-review-modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2>SLA Conversations - {userName} - {entryDate}</h2>
          <button className="icon-button" type="button" onClick={onClose}>x</button>
        </div>
        {loading ? <p className="field-help">Loading SLA cycles...</p> : null}
        {error ? <p className="form-message error">{error}</p> : null}
        {!loading && !error && data ? (
          <>
            <p className="field-help dailyEntry-sla-review-summary">{data.met_count}/{data.total_count} UNDER SLA</p>
            <div className="table-scroll">
              <table className="users-table dailyEntry-sla-review-table">
                <thead>
                  <tr>
                    <th>Buyer</th>
                    <th>Seller</th>
                    <th>Buyer Message</th>
                    <th>Replied</th>
                    <th>Response Time</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.length === 0 ? (
                    <tr><td colSpan={7}>No SLA cycles found for this date.</td></tr>
                  ) : data.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.buyer || '-'}</td>
                      <td>{item.seller || '-'}</td>
                      <td>{new Date(item.buyer_message_time).toLocaleString()}</td>
                      <td>{item.replied_time ? new Date(item.replied_time).toLocaleString() : '-'}</td>
                      <td>{formatDuration(item.response_duration_seconds)}</td>
                      <td>
                        <span className={`upload-status ${item.sla_met ? 'success' : 'error'}`}>{item.sla_met ? 'Met' : 'Missed'}</span>
                      </td>
                      <td>
                        <a className="icon-button" href={`/inbox?conversation_id=${encodeURIComponent(item.conversation_id)}`} title="Go to Conversation" aria-label="Go to Conversation">
                          <Icon name="message" />
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>
    </div>
  )
}

function AgentCard({ row, onChange, onReviewSla }) {
  const displayItems = useMemo(() => buildTaskDisplayItems(row.score_items), [row.score_items])
  const taskAverage = taskAveragePercent(row.score_items)
  const slaPerformance = slaPerformancePercent(row.sla_score, row.sla_total_count)
  const isMajor = row.error_level === 'MAJOR'
  const isLocked = row.status === 'success'
  const isDisabled = isLocked || isMajor

  function isTaskIncluded(item) {
    return item.status === 'ENTERED'
  }

  function toggleTaskInclusion(item) {
    if (isDisabled) return
    if (item.child_items?.length) {
      updateItems(item.child_items.map((child) => child.key), { status: isTaskIncluded(item) ? 'NOT_APPLICABLE' : 'ENTERED' }, false)
      return
    }
    updateItem(item.key, { status: isTaskIncluded(item) ? 'NOT_APPLICABLE' : 'ENTERED' }, false)
  }

  function patch(fields) {
    if (isLocked) return
    onChange(row.userId, (current) => {
      const next = { ...current, ...fields }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level, next.sla_total_count)
      return next
    })
  }

  function updateItem(key, patchFields, markManual = true) {
    updateItems([key], patchFields, markManual)
  }

  function updateItems(keys, patchFields, markManual = true) {
    if (isLocked) return
    const keySet = new Set(keys)
    onChange(row.userId, (current) => {
      // Spread patchFields over the existing item so fields we don't touch here -
      // notably `breakdown` and `activity_count` on the Other General Work row -
      // are preserved even after the Admin edits the score manually.
      const nextItems = current.score_items.map((item) => keySet.has(item.key) ? { ...item, ...patchFields, source: markManual && patchFields.value !== undefined ? 'MANUAL' : item.source } : item)
      const next = { ...current, score_items: nextItems }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level, next.sla_total_count)
      return next
    })
  }

  function updateDisplayItemScore(item, value) {
    if (item.child_items?.length) {
      updateGroupedScore(item, value)
      return
    }
    const status = value > 0 ? 'ENTERED' : (isTaskIncluded(item) ? 'ENTERED' : 'NOT_APPLICABLE')
    updateItem(item.key, { value, status })
  }

  function updateGroupedScore(group, value) {
    if (isLocked) return
    onChange(row.userId, (current) => {
      let remaining = value
      const childKeys = new Set(group.child_items.map((child) => child.key))
      const children = group.child_items
      const nextItems = current.score_items.map((item) => {
        if (!childKeys.has(item.key)) return item
        const childIndex = children.findIndex((child) => child.key === item.key)
        const isLast = childIndex === children.length - 1
        const childMax = number(item.max_score)
        const childValue = isLast ? clamp(remaining, childMax) : Math.min(childMax, remaining)
        remaining = Math.max(0, remaining - childValue)
        return { ...item, value: childValue, status: value > 0 ? 'ENTERED' : (isTaskIncluded(group) ? 'ENTERED' : 'NOT_APPLICABLE'), source: 'MANUAL' }
      })
      const next = { ...current, score_items: nextItems }
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level, next.sla_total_count)
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
      next.final_score_percent = calculate(next.score_items, next.sla_score, next.error_level, next.sla_total_count)
      return next
    })
  }

  return (
    <section className={`table-card dailyEntry-agent-card${isLocked ? ' locked' : ''}${isMajor ? ' major-error' : ''}`}>
      <div className="dailyEntry-card-header dailyEntry-agent-card-header">
        <label className="checkbox-field"><input type="checkbox" checked={row.selected} onChange={(event) => onChange(row.userId, (current) => ({ ...current, selected: event.target.checked }))} /></label>
        <div className="dailyEntry-agent-identity"><h3>{row.userName}</h3><small>{row.userEmail}</small></div>
        <div className="dailyEntry-agent-card-header-status">
          {isLocked ? <span className="upload-status success">Uploaded &amp; Locked</span> : null}
          {row.status === 'error' ? <span className="upload-status error">{row.statusMessage || 'Failed'}</span> : null}
          {isLocked ? <button className="unlock-button" type="button" onClick={() => onChange(row.userId, (current) => ({ ...current, status: 'idle', statusMessage: '' }))}>Unlock to Edit</button> : null}
        </div>
      </div>
      {isLocked ? <p className="field-help locked-help">This entry has been uploaded and is locked from editing. Click "Unlock to Edit" to make changes and re-upload.</p> : null}

      <section className="dailyEntry-task-box">
        <h3 className="dailyEntry-section-label">Tasks &amp; Scoring</h3>
        {(row.score_items || []).length === 0 ? <p className="field-help dailyEntry-empty-state">No subtasks assigned to this agent.</p> : null}
        {displayItems.map((item) => (
          <div className={`dailyEntry-dynamic-row${isTaskIncluded(item) ? '' : ' not-applicable'}`} key={item.key}>
            <div className="dailyEntry-dynamic-row-label">
              <div className="dailyEntry-dynamic-row-label-title">
                <strong>{item.label}</strong>
                {item.key === OTHER_GENERAL_WORK_KEY ? <OtherGeneralWorkInfo breakdown={item.breakdown} /> : null}
                {item.child_items?.length ? <SubtaskChildrenInfo children={item.child_items} /> : null}
              </div>
              <div className="dailyEntry-task-meta-line">
                <span className={`source-badge ${item.source === 'AUTO' ? 'source-auto' : 'source-manual'}`}>
                  {sourceLabel(item.source)}{item.source === 'AUTO' ? ` · ${item.activity_count ?? 0} handled` : ''}
                </span>
                <span className={`dailyEntry-count-status ${isTaskIncluded(item) ? 'included' : 'excluded'}`}>
                  {isTaskIncluded(item) ? 'Counted today' : 'Not counted today'}
                </span>
              </div>
            </div>
            <div className="dailyEntry-dynamic-row-score dailyEntry-dynamic-row-score-with-toggle">
              <div className="dailyEntry-score-input-line">
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  max={item.max_score}
                  disabled={isDisabled}
                  value={isMajor ? 0 : item.value}
                  onChange={(event) => {
                    const value = clamp(event.target.value, item.max_score)
                    updateDisplayItemScore(item, value)
                  }}
                />
                <span className="dailyEntry-score-max">/ {formatScore(item.max_score)} · {isTaskIncluded(item) ? `${formatPercent(taskPerformancePercent(item))}%` : 'N/A'}</span>
              </div>
              <button
                type="button"
                className={`dailyEntry-task-count-toggle ${isTaskIncluded(item) ? 'exclude' : 'include'}`}
                disabled={isDisabled}
                onClick={() => toggleTaskInclusion(item)}
                title={isTaskIncluded(item) ? "Exclude this task from today's PMS calculation" : "Include this task in today's PMS calculation, even if its score is 0"}
              >
                {isTaskIncluded(item) ? 'Exclude Today' : 'Count 0 Today'}
              </button>
            </div>
          </div>
        ))}
        <div className="dailyEntry-dynamic-row dailyEntry-sla-row">
          <div className="dailyEntry-dynamic-row-label">
            <strong>SLA Score</strong>
            <span className={`source-badge ${row.sla_auto_fetched ? 'source-auto' : 'source-manual'}`}>
              {row.sla_auto_fetched ? `AUTO FETCHED \u00b7 ${row.sla_met_count ?? 0}/${row.sla_total_count ?? 0} UNDER SLA` : 'Manual'}
            </span>
            {row.sla_total_count ? (
              <button type="button" className="secondary-button compact-action dailyEntry-sla-review-button" onClick={() => onReviewSla(row)}>
                Review SLA Conversations ({row.sla_total_count})
              </button>
            ) : null}
          </div>
          <div className="dailyEntry-dynamic-row-score">
            <input type="number" min="0" max={SLA_MAX} disabled={isDisabled} value={isMajor ? 0 : row.sla_score} onChange={(event) => patch({ sla_score: clamp(event.target.value, SLA_MAX), sla_auto_fetched: false })} />
            <span className="dailyEntry-score-max">/ {SLA_MAX}</span>
          </div>
        </div>
        <div className="dailyEntry-task-row final">
          <div className="dailyEntry-final-metric"><span>Task Average</span><strong>{isMajor ? '0%' : `${formatPercent(taskAverage)}%`}</strong></div>
          <div className="dailyEntry-final-metric"><span>SLA Performance</span><strong>{isMajor ? '0%' : `${formatPercent(slaPerformance)}%`}</strong></div>
          <div className="dailyEntry-final-metric dailyEntry-final-score"><span>Final Score</span><strong>{row.final_score_percent}%</strong></div>
        </div>
      </section>

      <section className="dailyEntry-details-box">
        <h3 className="dailyEntry-section-label">Day Details</h3>
        <div className="dailyEntry-form-row">
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
  const [slaReviewRow, setSlaReviewRow] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const eligibleRows = useMemo(() => rows.filter((row) => row.status !== 'success'), [rows])
  const selectedCount = useMemo(() => eligibleRows.filter((row) => row.selected).length, [eligibleRows])
  const lockedCount = rows.length - eligibleRows.length

  async function loadHistory(next = filters) {
    try {
      setHistory(await fetchDailyEntries(next))
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
      const response = await apiLoadDailyEntries({ entry_date: entryDate, user_id: agentFilter || undefined })
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
      const response = await uploadDailyEntries(entries)
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
      <main className="management-page dailyEntry-page">
        <div className="page-header"><div><h1>Daily Task Entry</h1><p>{isAdmin ? 'Load, review and upload dailyEntry entries for the team' : 'View your Daily Entry scores and history'}</p></div></div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <section className="dailyEntry-daily-entry-layout">
          {isAdmin ? (
            <section className="table-card dailyEntry-load-card">
              <div className="dailyEntry-card-header"><h2>Load Daily Entries</h2></div>
              <p className="field-help">Only Agent-role users are loaded here. Operations Managers and Admins are not included.</p>
              <div className="dailyEntry-form-row dailyEntry-load-controls">
                <label className="field"><span>Date</span><input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} /></label>
                <button className="primary-button compact-action" type="button" onClick={loadDailyEntries} disabled={loading}>{loading ? 'Loading...' : 'Load Daily Entries'}</button>
              </div>

              {loaded ? (
                <>
                  <div className="dailyEntry-bulk-actions">
                    <div className="dailyEntry-bulk-actions-select">
                      <button className="secondary-button compact-action" type="button" onClick={() => selectAll(true)}>Select All</button>
                      <button className="secondary-button compact-action" type="button" onClick={() => selectAll(false)}>Deselect All</button>
                      <span className="field-help dailyEntry-select-count">{selectedCount} of {eligibleRows.length} selected{lockedCount ? ` \u00b7 ${lockedCount} already uploaded` : ''}</span>
                    </div>
                    <div className="dailyEntry-bulk-actions-upload">
                      <button className="primary-button compact-action" type="button" onClick={() => upload('selected')} disabled={uploading || !selectedCount}>{uploading ? 'Uploading...' : 'Upload Selected'}</button>
                      <button className="primary-button compact-action" type="button" onClick={() => upload('all')} disabled={uploading || !eligibleRows.length}>{uploading ? 'Uploading...' : 'Upload All'}</button>
                    </div>
                  </div>
                  {rows.length === 0 ? <p className="field-help dailyEntry-empty-state">No active agents found for this selection.</p> : null}
                  <div className="dailyEntry-agent-cards">
                    {rows.map((row) => <AgentCard key={row.userId} row={row} onChange={updateRow} onReviewSla={setSlaReviewRow} />)}
                  </div>
                </>
              ) : null}
            </section>
          ) : null}
          <section className="table-card dailyEntry-history-card">
            <div className="dailyEntry-card-header"><h2>{isAdmin ? 'Team dailyEntry History' : 'My History'}</h2></div>
            <form className="dailyEntry-history-filters" onSubmit={applyFilters}>
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
      {slaReviewRow ? (
        <SlaReviewModal
          userId={slaReviewRow.userId}
          userName={slaReviewRow.userName}
          entryDate={slaReviewRow.entry_date}
          onClose={() => setSlaReviewRow(null)}
        />
      ) : null}
    </AppLayout>
  )
}

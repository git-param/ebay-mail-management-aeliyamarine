import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { fetchUsers } from '../../services/userApi'
import {
  cancelLeaveRequest,
  createLeaveRequest,
  fetchLeaveBalances,
  fetchLeaveAdminSummary,
  fetchLeaveCarryForward,
  fetchLeavePolicy,
  fetchLeaveRequests,
  reviewLeaveRequest,
  updateLeaveAdminSummary,
  updateLeaveCarryForward,
  updateLeavePolicy,
} from '../../services/leaveManagementApi'
import { normalizeRole } from '../../utils/roles'

import './leave_management.css'

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

function currentMonth() {
  const now = new Date()
  return {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
  }
}

function monthOptions() {
  const now = new Date()
  return Array.from({ length: 18 }, (_, index) => {
    const d = new Date(now.getFullYear(), now.getMonth() - index, 1)
    return {
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      label: `${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`,
    }
  })
}

function monthValue(month) {
  return `${month.year}-${String(month.month).padStart(2, '0')}`
}

function parseMonth(value) {
  const [year, month] = value.split('-').map(Number)
  return { year, month }
}

function fmt(value) {
  const number = Number(value || 0)
  return Number.isInteger(number) ? String(number) : number.toFixed(1)
}

function numericValue(value) {
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : 0
}

function statusClass(status) {
  return `leaveModule-status leaveModule-status-${String(status || '').toLowerCase()}`
}

function percentValue(used, total) {
  const usedValue = Number(used || 0)
  const totalValue = Number(total || 0)
  if (!Number.isFinite(usedValue) || !Number.isFinite(totalValue) || totalValue <= 0) return 0
  return Math.max(0, Math.min(100, (usedValue / totalValue) * 100))
}

function leaveLabel(value) {
  return String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function dateTimeLabel(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

function formatLeaveDate(value) {
  if (!value) return '[Date]'
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

function leaveDateText(form) {
  const startDate = formatLeaveDate(form.start_date)
  const endDate = formatLeaveDate(form.end_date)

  if (form.leave_type === 'PAID' && form.end_date && form.end_date !== form.start_date) {
    return `${startDate} - ${endDate}`
  }

  return startDate
}

function formatTime(value) {
  if (!value) return ''
  const [hours, minutes] = value.split(':').map(Number)
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return value
  const date = new Date()
  date.setHours(hours, minutes, 0, 0)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function officeTimeRange(policy) {
  const start = formatTime(policy?.office_start_time) || '09:30 AM'
  const end = formatTime(policy?.office_end_time) || '06:30 PM'
  return `${start} - ${end}`
}

function shortLeaveTimeRange(pattern) {
  if (pattern === 'EARLY_EXIT_WITHOUT_BREAK') 
    return '03:30 PM - 06:30 PM'
  if (pattern === 'EARLY_EXIT_WITH_BREAK') 
    return '04:30 PM - 06:30 PM'
  return '09:30 AM - 11:30 AM'
}

function leaveEmailDetails(form, policy) {
  const fullDayTime = officeTimeRange(policy)
  const firstHalfEnd = formatTime(policy?.first_half_end_time) || '01:30 PM'
  const secondHalfStart = formatTime(policy?.second_half_start_time) || '02:30 PM'
  const officeEnd = formatTime(policy?.office_end_time) || '06:30 PM'
  const officeStart = formatTime(policy?.office_start_time) || '09:30 AM'

  if (form.leave_type === 'SHORT') {
    return {
      type: 'Short Leave',
      time: shortLeaveTimeRange(form.short_leave_pattern),
    }
  }

  if (form.leave_type === 'INSTANCE') {
    if (form.instance_kind === 'EARLY_DEPARTURE') {
      return {
        type: 'Second Half Leave',
        time: `${secondHalfStart} - ${officeEnd}`,
      }
    }

    return {
      type: 'First Half Leave',
      time: `${officeStart} - ${firstHalfEnd}`,
    }
  }

  if (form.day_part === 'HALF') {
    if (form.half_day_part === 'SECOND') {
      return {
        type: 'Second Half Leave',
        time: `${secondHalfStart} - ${officeEnd}`,
      }
    }

    return {
      type: 'First Half Leave',
      time: `${officeStart} - ${firstHalfEnd}`,
    }
  }

  return {
    type: 'Full Day Leave',
    time: fullDayTime,
  }
}

function buildLeaveEmailTemplate(form, policy) {
  const details = leaveEmailDetails(form, policy)
  const date = leaveDateText(form)
  const leaveType = form.leave_type === 'PAID' && form.day_part === 'FULL' && form.end_date && form.end_date !== form.start_date
    ? 'Full Day Leaves'
    : details.type
  const reason = form.reason.trim() || '[reason - optional]'

  return [
    `Subject: ${leaveType} (${details.time}) - ${date}`,
    '',
    'Dear [Manager\'s Name / Team],',
    '',
    `I would like to request a ${leaveType} on ${date}, ${details.time} due to ${reason}.`,
    '',
    'Please let me know if any further information is required. I will ensure all responsibilities are managed accordingly.',
  ].join('\n')
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Fall back for blocked Clipboard API contexts.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  try {
    if (!document.execCommand('copy')) {
      throw new Error('Clipboard copy failed')
    }
  } finally {
    document.body.removeChild(textarea)
  }
}

function emptyForm() {
  return {
    leave_type: 'PAID',
    start_date: '',
    end_date: '',
    day_part: 'FULL',
    half_day_part: 'FIRST',
    instance_kind: 'LATE_ARRIVAL',
    short_leave_pattern: 'LATE_LOGIN',
    reason: '',
  }
}

function LeaveManagement({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role)
  const isAdmin = role === 'ADMIN'
  const [selectedMonth, setSelectedMonth] = useState(currentMonth)
  const [policy, setPolicy] = useState(null)
  const [policyDraft, setPolicyDraft] = useState({})
  const [requests, setRequests] = useState([])
  const [adminSummary, setAdminSummary] = useState([])
  const [balances, setBalances] = useState([])
  const [users, setUsers] = useState([])
  const [carryForwardUserId, setCarryForwardUserId] = useState('')
  const [carryForwardDraft, setCarryForwardDraft] = useState('0')
  const [carryForwardSaving, setCarryForwardSaving] = useState(false)
  const [filters, setFilters] = useState({ leave_type: '', status: '', user_id: '' })
  const [form, setForm] = useState(emptyForm)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [copyState, setCopyState] = useState('idle')
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [summarySaving, setSummarySaving] = useState(false)
  const options = useMemo(() => monthOptions(), [])
  const leaveEmailTemplate = useMemo(() => buildLeaveEmailTemplate(form, policy), [form, policy])

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [policyData, requestData, balanceData, summaryData] = await Promise.all([
        fetchLeavePolicy(),
        fetchLeaveRequests({
          year: selectedMonth.year,
          month: selectedMonth.month,
          leave_type: filters.leave_type,
          status: filters.status,
          user_id: isAdmin ? filters.user_id : '',
        }),
        fetchLeaveBalances({
          year: selectedMonth.year,
          month: selectedMonth.month,
          user_id: isAdmin ? filters.user_id : '',
        }),
        isAdmin
          ? fetchLeaveAdminSummary({
            year: selectedMonth.year,
            month: selectedMonth.month,
          })
          : Promise.resolve([]),
      ])
      setPolicy(policyData)
      setPolicyDraft(policyData)
      setRequests(requestData.items || [])
      setBalances(balanceData || [])
      setAdminSummary(summaryData || [])
    } catch (err) {
      setError(err?.message || 'Failed to load leave data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [selectedMonth.year, selectedMonth.month, filters.leave_type, filters.status, filters.user_id])

  useEffect(() => {
    if (!isAdmin) return
    let active = true
    fetchUsers()
      .then((items) => {
        if (active) setUsers((items || []).filter((user) => normalizeRole(user.role) === 'AGENT'))
      })
      .catch(() => {
        if (active) setUsers([])
      })
    return () => {
      active = false
    }
  }, [isAdmin])

  useEffect(() => {
    if (!isAdmin || !users.length) return
    setCarryForwardUserId((current) => current || users[0].id)
  }, [isAdmin, users])

  useEffect(() => {
    if (!isAdmin || !carryForwardUserId) return
    let active = true
    fetchLeaveCarryForward({
      user_id: carryForwardUserId,
      year: selectedMonth.year,
      month: selectedMonth.month,
    })
      .then((data) => {
        if (active) setCarryForwardDraft(String(data.carry_forward ?? 0))
      })
      .catch(() => {
        if (active) setCarryForwardDraft('0')
      })
    return () => {
      active = false
    }
  }, [isAdmin, carryForwardUserId, selectedMonth.year, selectedMonth.month])

  const myBalance = balances[0]
  const paidPool = Number(myBalance?.paid_accrued || 0)
  const paidUsed = Number(myBalance?.paid_used || 0)
  const instanceLimit = Number(policy?.instance_limit || 0)
  const shortLeaveLimit = Number(policy?.short_leave_limit || 0)
  const pmsImpact = (myBalance?.pms_attendance_deduction || 0) + (myBalance?.pms_punctuality_deduction || 0)

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
    setCopyState('idle')
  }

  function updateSummaryRow(userId, key, value) {
    setAdminSummary((items) => items.map((item) => (
      item.user_id === userId
        ? { ...item, [key]: value }
        : item
    )))
  }

  async function submitRequest(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    try {
      // Build only the fields relevant to the selected leave type.
      // This avoids sending empty time strings for paid leave, which FastAPI/Pydantic rejects.
      const payload = {
        leave_type: form.leave_type,
        start_date: form.start_date,
        end_date: ['INSTANCE', 'SHORT'].includes(form.leave_type) ? form.start_date : (form.end_date || form.start_date),
        reason: form.reason.trim(),
      }

      if (form.leave_type === 'PAID') {
        payload.day_part = form.day_part
      }

      if (form.leave_type === 'INSTANCE') {
        payload.instance_kind = form.instance_kind
      }

      if (form.leave_type === 'SHORT') {
        payload.short_leave_pattern = form.short_leave_pattern
      }
      await createLeaveRequest(payload)
      setForm(emptyForm())
      setMessage('Leave request submitted.')
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to submit leave request.')
    }
  }

  async function copyLeaveEmailTemplate() {
    setError('')
    try {
      await copyTextToClipboard(leaveEmailTemplate)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 2500)
    } catch (err) {
      setCopyState('failed')
      setError(err?.message || 'Unable to copy leave email template.')
    }
  }

  async function review(requestId, status) {
    setError('')
    setMessage('')
    try {
      await reviewLeaveRequest(requestId, { status })
      setSelectedRequest(null)
      setMessage(`Leave request ${status.toLowerCase()}.`)
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to review leave request.')
    }
  }

  async function cancel(requestId) {
    setError('')
    setMessage('')
    try {
      await cancelLeaveRequest(requestId)
      setMessage('Leave request cancelled.')
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to cancel leave request.')
    }
  }

  async function savePolicy(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    try {
      const payload = {
        paid_leave_per_month: Number(policyDraft.paid_leave_per_month),
        instance_limit: Number(policyDraft.instance_limit),
        short_leave_limit: Number(policyDraft.short_leave_limit),
        instance_max_minutes: Number(policyDraft.instance_max_minutes),
        short_leave_max_minutes: Number(policyDraft.short_leave_max_minutes),
        office_start_time: policyDraft.office_start_time,
        office_end_time: policyDraft.office_end_time,
        attendance_deduction_per_excess: Number(policyDraft.attendance_deduction_per_excess),
        punctuality_deduction_per_extra_instance: Number(policyDraft.punctuality_deduction_per_extra_instance),
        short_leave_over_limit_action: 'BLOCK',
      }
      const saved = await updateLeavePolicy(payload)
      setPolicy(saved)
      setPolicyDraft(saved)
      setMessage('Leave policy updated.')
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to update leave policy.')
    }
  }

  async function saveAdminSummary() {
    setError('')
    setMessage('')
    setSummarySaving(true)
    try {
      const saved = await updateLeaveAdminSummary({
        year: selectedMonth.year,
        month: selectedMonth.month,
        items: adminSummary
          .filter((item) => item.user_id)
          .map((item) => ({
            user_id: item.user_id,
            paid_leaves: numericValue(item.paid_leaves),
            unpaid_leaves: numericValue(item.unpaid_leaves),
            adh: Math.floor(numericValue(item.adh)),
          })),
      })
      setAdminSummary(saved || [])
      setMessage('Leave summary updated.')
    } catch (err) {
      setError(err?.message || 'Failed to update leave summary.')
    } finally {
      setSummarySaving(false)
    }
  }

  async function saveCarryForward(event) {
    event.preventDefault()
    if (!carryForwardUserId) return
    setError('')
    setMessage('')
    setCarryForwardSaving(true)
    try {
      const saved = await updateLeaveCarryForward({
        user_id: carryForwardUserId,
        year: selectedMonth.year,
        month: selectedMonth.month,
        carry_forward: numericValue(carryForwardDraft),
      })
      setCarryForwardDraft(String(saved.carry_forward ?? 0))
      setMessage('Carry forward updated.')
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to update carry forward.')
    } finally {
      setCarryForwardSaving(false)
    }
  }

  return (
    <AppLayout activePage="Leave Management" currentUser={currentUser} onLogout={onLogout}>
      <main className="leaveModule-page">
        <header className="leaveModule-header">
          <div>
            <span className="leaveModule-eyebrow">People Operations</span>
            <h1>Leave Management</h1>
            <p>Integrated leave tracking for balances, approval flow, audit, and PMS attendance impact.</p>
          </div>
          <select value={monthValue(selectedMonth)} onChange={(event) => setSelectedMonth(parseMonth(event.target.value))}>
            {options.map((item) => <option key={monthValue(item)} value={monthValue(item)}>{item.label}</option>)}
          </select>
        </header>

        {error ? <div className="leaveModule-message error">{error}</div> : null}
        {message ? <div className="leaveModule-message success">{message}</div> : null}

        <section className="leaveModule-summary">
          <div className="leaveModule-kpi leaveModule-kpi-paid">
            <div className="leaveModule-kpi-topline">
              <span>Paid Available</span>
              <b><Icon name="calendar" /></b>
            </div>
            <strong>{fmt(myBalance?.paid_available)}</strong>
            <small>{fmt(myBalance?.paid_used)} used from {fmt(myBalance?.paid_accrued)} available pool</small>
            <div className="leaveModule-progress" aria-hidden="true">
              <span style={{ width: `${percentValue(paidUsed, paidPool)}%` }} />
            </div>
          </div>
          <div className="leaveModule-kpi leaveModule-kpi-instance">
            <div className="leaveModule-kpi-topline">
              <span>Instances</span>
              <b><Icon name="clock" /></b>
            </div>
            <strong>{myBalance?.instance_used ?? 0}</strong>
            <small>{myBalance?.instance_remaining ?? 0} without PMS penalty left</small>
            <div className="leaveModule-progress" aria-hidden="true">
              <span style={{ width: `${percentValue(myBalance?.instance_used, instanceLimit)}%` }} />
            </div>
          </div>
          <div className="leaveModule-kpi leaveModule-kpi-short">
            <div className="leaveModule-kpi-topline">
              <span>Short Leave</span>
              <b><Icon name="reply" /></b>
            </div>
            <strong>{myBalance?.short_used ?? 0}</strong>
            <small>{myBalance?.short_remaining ?? 0} left this month</small>
            <div className="leaveModule-progress" aria-hidden="true">
              <span style={{ width: `${percentValue(myBalance?.short_used, shortLeaveLimit)}%` }} />
            </div>
          </div>
          <div className="leaveModule-kpi leaveModule-kpi-pms">
            <div className="leaveModule-kpi-topline">
              <span>PMS Impact</span>
              <b><Icon name="pms" /></b>
            </div>
            <strong>{fmt(pmsImpact)}</strong>
            <small>Attendance & punctuality only</small>
          </div>
        </section>

        <section className="leaveModule-grid">
          <form className="leaveModule-panel leaveModule-form" onSubmit={submitRequest}>
            <div className="leaveModule-panel-header">
              <h2>Apply Leave</h2>
            </div>
            <div className="leaveModule-form-grid">
              <label>
                Type
                <select value={form.leave_type} onChange={(event) => updateForm('leave_type', event.target.value)}>
                  <option value="PAID">Paid Leave</option>
                  <option value="INSTANCE">Instance Leave</option>
                  <option value="SHORT">Short Leave</option>
                </select>
              </label>
              {form.leave_type === 'PAID' ? (
                <label>
                  Day
                  <select value={form.day_part} onChange={(event) => updateForm('day_part', event.target.value)}>
                    <option value="FULL">Full day</option>
                    <option value="HALF">Half day</option>
                  </select>
                </label>
              ) : null}
              {form.leave_type === 'PAID' && form.day_part === 'HALF' ? (
                <label>
                  Half
                  <select value={form.half_day_part} onChange={(event) => updateForm('half_day_part', event.target.value)}>
                    <option value="FIRST">First half</option>
                    <option value="SECOND">Second half</option>
                  </select>
                </label>
              ) : null}
              {form.leave_type === 'INSTANCE' ? (
                <label>
                  Instance
                  <select value={form.instance_kind} onChange={(event) => updateForm('instance_kind', event.target.value)}>
                    <option value="LATE_ARRIVAL">Late arrival</option>
                    <option value="EARLY_DEPARTURE">Early departure</option>
                  </select>
                </label>
              ) : null}
              {form.leave_type === 'SHORT' ? (
                <label>
                  Pattern
                  <select value={form.short_leave_pattern} onChange={(event) => updateForm('short_leave_pattern', event.target.value)}>
                    <option value="LATE_LOGIN">Late login</option>
                    <option value="MID_DAY_LEAVE">Mid-day leave</option>
                    <option value="EARLY_EXIT_WITHOUT_BREAK">Early exit without break</option>
                    <option value="EARLY_EXIT_WITH_BREAK">Early exit with break</option>
                  </select>
                </label>
              ) : null}
              <label>
                {['INSTANCE', 'SHORT'].includes(form.leave_type) ? 'Date' : 'Start Date'}
                <input type="date" value={form.start_date} onChange={(event) => updateForm('start_date', event.target.value)} required />
              </label>
              {form.leave_type === 'PAID' ? (
                <label>
                  End Date
                  <input type="date" value={form.end_date} onChange={(event) => updateForm('end_date', event.target.value)} />
                </label>
              ) : null}
              <label className="leaveModule-span">
                Reason
                <textarea value={form.reason} onChange={(event) => updateForm('reason', event.target.value)} required />
              </label>
            </div>
            <div className="leaveModule-form-actions">
              <button className="leaveModule-primary" type="submit"><Icon name="plus" /> Submit Request</button>
              <button className="leaveModule-secondary" type="button" onClick={copyLeaveEmailTemplate}>
                <Icon name={copyState === 'copied' ? 'activate' : 'copy'} />
                {copyState === 'copied' ? 'Copied' : 'Copy Email'}
              </button>
            </div>
            {copyState === 'failed' ? <p className="leaveModule-copy-feedback">Could not copy email template.</p> : null}
          </form>

          <section className="leaveModule-panel">
            <div className="leaveModule-panel-header">
              <h2>Requests</h2>
              <div className="leaveModule-filters">
                {isAdmin ? (
                  <select value={filters.user_id} onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}>
                    <option value="">All employees</option>
                    {users.map((user) => <option key={user.id} value={user.id}>{user.name || user.email}</option>)}
                  </select>
                ) : null}
                <select value={filters.leave_type} onChange={(event) => setFilters((current) => ({ ...current, leave_type: event.target.value }))}>
                  <option value="">All types</option>
                  <option value="PAID">Paid</option>
                  <option value="INSTANCE">Instance</option>
                  <option value="SHORT">Short</option>
                </select>
                <select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
                  <option value="">All statuses</option>
                  <option value="PENDING">Pending</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                  <option value="CANCELLED">Cancelled</option>
                </select>
              </div>
            </div>
            <div className="leaveModule-table-wrap">
              <table className="leaveModule-table">
                <thead>
                  <tr>
                    {isAdmin ? <th>Employee</th> : null}
                    <th>Type</th>
                    <th>Date</th>
                    <th>Duration</th>
                    <th>Status</th>
                    <th>PMS</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((item) => (
                    <tr
                      key={item.id}
                      className={isAdmin ? 'leaveModule-clickable-row' : undefined}
                      onClick={() => {
                        if (isAdmin) setSelectedRequest(item)
                      }}
                    >
                      {isAdmin ? <td>{item.user_name || item.user_email}</td> : null}
                      <td>{leaveLabel(item.leave_type)}</td>
                      <td>{item.start_date}{item.end_date !== item.start_date ? ` to ${item.end_date}` : ''}</td>
                      <td>{item.leave_type === 'PAID' ? `${fmt(item.duration_days)} day` : 'Single date'}</td>
                      <td><span className={statusClass(item.status)}>{leaveLabel(item.status)}</span></td>
                      <td>{fmt((item.pms_attendance_deduction || 0) + (item.pms_punctuality_deduction || 0))}</td>
                      <td>
                        {isAdmin && item.status === 'PENDING' ? (
                          <div className="leaveModule-row-actions">
                            <button type="button" onClick={(event) => { event.stopPropagation(); review(item.id, 'APPROVED') }}>Approve</button>
                            <button type="button" onClick={(event) => { event.stopPropagation(); review(item.id, 'REJECTED') }}>Reject</button>
                          </div>
                        ) : null}
                        {!isAdmin && item.status === 'PENDING' ? <button type="button" onClick={(event) => { event.stopPropagation(); cancel(item.id) }}>Cancel</button> : null}
                      </td>
                    </tr>
                  ))}
                  {!requests.length ? (
                    <tr className="leaveModule-empty-row">
                      <td colSpan={isAdmin ? 7 : 6}>
                        {loading ? (
                          <div className="leaveModule-skeleton">Loading leave requests...</div>
                        ) : (
                          <div className="leaveModule-empty-state">
                            <Icon name="calendar" />
                            <strong>No leave requests yet</strong>
                            <span>Approved and pending requests will appear here.</span>
                          </div>
                        )}
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </section>

        {isAdmin ? (
          <section className="leaveModule-panel leaveModule-admin-summary">
            <div className="leaveModule-panel-header">
              <div>
                <h2>Monthly Leave Summary</h2>
                <p className="leaveModule-note">Paid and unpaid leaves are fetched from approved paid leave requests for the selected month. ADH is maintained by admin.</p>
              </div>
              <div className="leaveModule-summary-actions">
                <button className="leaveModule-primary" type="button" onClick={saveAdminSummary} disabled={summarySaving}>
                  {summarySaving ? 'Updating...' : 'Update'}
                </button>
              </div>
            </div>
            <div className="leaveModule-table-wrap">
              <table className="leaveModule-table leaveModule-summary-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Paid Leaves</th>
                    <th>Unpaid leaves</th>
                    <th>ADH</th>
                  </tr>
                </thead>
                <tbody>
                  {adminSummary.map((item) => (
                    <tr key={item.user_id}>
                      <td>
                        {item.employee}
                        {item.is_overridden ? <small className="leaveModule-override-label">Edited</small> : null}
                      </td>
                      <td>
                        <input type="number" min="0" step="0.5" value={item.paid_leaves} onChange={(event) => updateSummaryRow(item.user_id, 'paid_leaves', event.target.value)} />
                      </td>
                      <td>
                        <input type="number" min="0" step="0.5" value={item.unpaid_leaves} onChange={(event) => updateSummaryRow(item.user_id, 'unpaid_leaves', event.target.value)} />
                      </td>
                      <td>
                        <input type="number" min="0" step="1" value={item.adh} onChange={(event) => updateSummaryRow(item.user_id, 'adh', event.target.value)} />
                      </td>
                    </tr>
                  ))}
                  {!adminSummary.length ? (
                    <tr>
                      <td colSpan={4}>No employees found.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {isAdmin ? (
          <section className="leaveModule-panel leaveModule-policy">
            <div className="leaveModule-panel-header">
              <h2>Policy Configuration</h2>
            </div>
            <form className="leaveModule-policy-grid" onSubmit={saveCarryForward}>
              <label>
                Employee
                <select value={carryForwardUserId} onChange={(event) => setCarryForwardUserId(event.target.value)}>
                  {users.map((user) => <option key={user.id} value={user.id}>{user.name || user.email}</option>)}
                </select>
              </label>
              <label>
                Carry Forward
                <input type="number" min="0" step="0.5" value={carryForwardDraft} onChange={(event) => setCarryForwardDraft(event.target.value)} />
              </label>
              <button className="leaveModule-primary" type="submit" disabled={!carryForwardUserId || carryForwardSaving}>
                {carryForwardSaving ? 'Saving...' : 'Save Carry Forward'}
              </button>
            </form>
            <p className="leaveModule-note">Carry forward is set manually per employee for the selected month. It is used before unpaid leave, along with that month's paid allowance.</p>
            <form className="leaveModule-policy-grid" onSubmit={savePolicy}>
              {[
                ['paid_leave_per_month', 'Paid / Month', 'number'],
                ['instance_limit', 'Instance Limit', 'number'],
                ['short_leave_limit', 'Short Limit', 'number'],
                ['instance_max_minutes', 'Instance Max Minutes', 'number'],
                ['short_leave_max_minutes', 'Short Max Minutes', 'number'],
                ['office_start_time', 'Office Start', 'time'],
                ['office_end_time', 'Office End', 'time'],
                ['attendance_deduction_per_excess', 'Attendance Deduction', 'number'],
                ['punctuality_deduction_per_extra_instance', 'Punctuality Deduction', 'number'],
              ].map(([key, label, type]) => (
                <label key={key}>
                  {label}
                  <input
                    type={type}
                    step={type === 'number' ? '0.5' : undefined}
                    value={policyDraft?.[key] ?? ''}
                    onChange={(event) => setPolicyDraft((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </label>
              ))}
              <button className="leaveModule-primary" type="submit">Save Policy</button>
            </form>
          </section>
        ) : null}

        {isAdmin && selectedRequest ? (
          <div className="leaveModule-modal-backdrop" onClick={() => setSelectedRequest(null)}>
            <section className="leaveModule-modal" onClick={(event) => event.stopPropagation()}>
              <div className="leaveModule-modal-header">
                <div>
                  <h2>Leave Request</h2>
                  <p>{selectedRequest.user_name || selectedRequest.user_email}</p>
                </div>
                <button type="button" aria-label="Close" onClick={() => setSelectedRequest(null)}>×</button>
              </div>
              <dl className="leaveModule-detail-grid">
                <div>
                  <dt>Type</dt>
                  <dd>{leaveLabel(selectedRequest.leave_type)}</dd>
                </div>
                <div>
                  <dt>Date</dt>
                  <dd>{selectedRequest.start_date}{selectedRequest.end_date !== selectedRequest.start_date ? ` to ${selectedRequest.end_date}` : ''}</dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>{selectedRequest.leave_type === 'PAID' ? `${fmt(selectedRequest.duration_days)} day` : 'Single date'}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd><span className={statusClass(selectedRequest.status)}>{leaveLabel(selectedRequest.status)}</span></dd>
                </div>
                <div>
                  <dt>Handled At</dt>
                  <dd>{dateTimeLabel(selectedRequest.reviewed_at)}</dd>
                </div>
              </dl>
              <div className="leaveModule-reason-box">
                <span>Reason</span>
                <p>{selectedRequest.reason || 'No reason provided.'}</p>
              </div>
              {selectedRequest.status === 'PENDING' ? (
                <div className="leaveModule-modal-actions">
                  <button type="button" onClick={() => review(selectedRequest.id, 'REJECTED')}>Reject</button>
                  <button type="button" onClick={() => review(selectedRequest.id, 'APPROVED')}>Approve</button>
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
      </main>
    </AppLayout>
  )
}

export default LeaveManagement

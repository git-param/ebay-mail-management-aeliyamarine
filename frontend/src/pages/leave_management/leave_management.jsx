import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { fetchUsers } from '../../services/userApi'
import {
  cancelLeaveRequest,
  createLeaveRequest,
  fetchLeaveBalances,
  fetchLeavePolicy,
  fetchLeaveRequests,
  reviewLeaveRequest,
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

function statusClass(status) {
  return `leaveModule-status leaveModule-status-${String(status || '').toLowerCase()}`
}

function leaveLabel(value) {
  return String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function emptyForm() {
  return {
    leave_type: 'PAID',
    start_date: '',
    end_date: '',
    day_part: 'FULL',
    instance_kind: 'LATE_ARRIVAL',
    short_leave_pattern: 'LATE_LOGIN',
    start_time: '',
    end_time: '',
    duration_minutes: '',
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
  const [balances, setBalances] = useState([])
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({ leave_type: '', status: '', user_id: '' })
  const [form, setForm] = useState(emptyForm)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const options = useMemo(monthOptions, [])

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [policyData, requestData, balanceData] = await Promise.all([
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
      ])
      setPolicy(policyData)
      setPolicyDraft(policyData)
      setRequests(requestData.items || [])
      setBalances(balanceData || [])
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
        if (active) setUsers(items || [])
      })
      .catch(() => {
        if (active) setUsers([])
      })
    return () => {
      active = false
    }
  }, [isAdmin])

  const myBalance = balances[0]

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function submitRequest(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    try {
      const payload = {
        ...form,
        end_date: form.end_date || form.start_date,
        duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : undefined,
      }
      if (payload.leave_type !== 'PAID') delete payload.day_part
      if (payload.leave_type !== 'INSTANCE') delete payload.instance_kind
      if (payload.leave_type !== 'SHORT') delete payload.short_leave_pattern
      await createLeaveRequest(payload)
      setForm(emptyForm())
      setMessage('Leave request submitted.')
      await loadData()
    } catch (err) {
      setError(err?.message || 'Failed to submit leave request.')
    }
  }

  async function review(requestId, status) {
    setError('')
    setMessage('')
    try {
      await reviewLeaveRequest(requestId, { status })
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
        break_start_time: policyDraft.break_start_time || null,
        break_end_time: policyDraft.break_end_time || null,
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

  return (
    <AppLayout activePage="Leave Management" currentUser={currentUser} onLogout={onLogout}>
      <main className="leaveModule-page">
        <header className="leaveModule-header">
          <div>
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
          <div>
            <span>Paid Available</span>
            <strong>{fmt(myBalance?.paid_available)}</strong>
            <small>{fmt(myBalance?.paid_used)} used from {fmt(myBalance?.paid_accrued)} accrued</small>
          </div>
          <div>
            <span>Instances</span>
            <strong>{myBalance?.instance_used ?? 0}</strong>
            <small>{myBalance?.instance_remaining ?? 0} without PMS penalty left</small>
          </div>
          <div>
            <span>Short Leave</span>
            <strong>{myBalance?.short_used ?? 0}</strong>
            <small>{myBalance?.short_remaining ?? 0} left this month</small>
          </div>
          <div>
            <span>PMS Impact</span>
            <strong>{fmt((myBalance?.pms_attendance_deduction || 0) + (myBalance?.pms_punctuality_deduction || 0))}</strong>
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
                    <option value="EARLY_EXIT">Early exit</option>
                    <option value="EARLY_EXIT_WITH_BREAK">Early exit with break</option>
                  </select>
                </label>
              ) : null}
              <label>
                Start Date
                <input type="date" value={form.start_date} onChange={(event) => updateForm('start_date', event.target.value)} required />
              </label>
              <label>
                End Date
                <input type="date" value={form.end_date} onChange={(event) => updateForm('end_date', event.target.value)} />
              </label>
              {form.leave_type !== 'PAID' ? (
                <>
                  <label>
                    Start Time
                    <input type="time" value={form.start_time} onChange={(event) => updateForm('start_time', event.target.value)} required />
                  </label>
                  <label>
                    End Time
                    <input type="time" value={form.end_time} onChange={(event) => updateForm('end_time', event.target.value)} required />
                  </label>
                </>
              ) : null}
              <label className="leaveModule-span">
                Reason
                <textarea value={form.reason} onChange={(event) => updateForm('reason', event.target.value)} required />
              </label>
            </div>
            <button className="leaveModule-primary" type="submit"><Icon name="plus" /> Submit Request</button>
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
                    <tr key={item.id}>
                      {isAdmin ? <td>{item.user_name || item.user_email}</td> : null}
                      <td>{leaveLabel(item.leave_type)}</td>
                      <td>{item.start_date}{item.end_date !== item.start_date ? ` to ${item.end_date}` : ''}</td>
                      <td>{item.leave_type === 'PAID' ? `${fmt(item.duration_days)} day` : `${item.duration_minutes} min`}</td>
                      <td><span className={statusClass(item.status)}>{leaveLabel(item.status)}</span></td>
                      <td>{fmt((item.pms_attendance_deduction || 0) + (item.pms_punctuality_deduction || 0))}</td>
                      <td>
                        {isAdmin && item.status === 'PENDING' ? (
                          <div className="leaveModule-row-actions">
                            <button type="button" onClick={() => review(item.id, 'APPROVED')}>Approve</button>
                            <button type="button" onClick={() => review(item.id, 'REJECTED')}>Reject</button>
                          </div>
                        ) : null}
                        {!isAdmin && item.status === 'PENDING' ? <button type="button" onClick={() => cancel(item.id)}>Cancel</button> : null}
                      </td>
                    </tr>
                  ))}
                  {!requests.length ? (
                    <tr>
                      <td colSpan={isAdmin ? 7 : 6}>{loading ? 'Loading...' : 'No leave requests found.'}</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </section>

        {isAdmin ? (
          <section className="leaveModule-panel leaveModule-policy">
            <div className="leaveModule-panel-header">
              <h2>Policy Configuration</h2>
            </div>
            <form className="leaveModule-policy-grid" onSubmit={savePolicy}>
              {[
                ['paid_leave_per_month', 'Paid / Month', 'number'],
                ['instance_limit', 'Instance Limit', 'number'],
                ['short_leave_limit', 'Short Limit', 'number'],
                ['instance_max_minutes', 'Instance Max Minutes', 'number'],
                ['short_leave_max_minutes', 'Short Max Minutes', 'number'],
                ['office_start_time', 'Office Start', 'time'],
                ['office_end_time', 'Office End', 'time'],
                ['break_start_time', 'Break Start', 'time'],
                ['break_end_time', 'Break End', 'time'],
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
            <p className="leaveModule-note">Carry-forward starts at August 2026 only; earlier months are intentionally excluded.</p>
          </section>
        ) : null}
      </main>
    </AppLayout>
  )
}

export default LeaveManagement

import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { fetchUsers } from '../../services/userApi'
import {
  cancelLeaveRequest,
  createLeaveRequest,
  fetchLeaveBalances,
  fetchLeaveAdminSummary,
  fetchLeavePolicy,
  fetchLeaveRequests,
  reviewLeaveRequest,
  updateLeaveAdminSummary,
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

function leaveLabel(value) {
  return String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function dateTimeLabel(value) {
  return value ? new Date(value).toLocaleString() : '-'
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
  const [filters, setFilters] = useState({ leave_type: '', status: '', user_id: '' })
  const [form, setForm] = useState(emptyForm)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [summarySaving, setSummarySaving] = useState(false)
  const options = useMemo(monthOptions, [])

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

  const myBalance = balances[0]

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
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
            <p className="leaveModule-note">Carry-forward starts at August 2026 only; earlier months are intentionally excluded.</p>
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

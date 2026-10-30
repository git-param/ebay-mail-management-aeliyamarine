import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { exportBreakReport, fetchBreakEmployees, fetchBreakHistory, fetchBreakOverview } from '../../services/breakManagementApi'
import { normalizeRole } from '../../utils/roles'
import BreakActionButton from './BreakActionButton'

import './break_maagement.css'

const DAILY_BREAK_ALLOWANCE_MINUTES = 60

const QUICK_RANGES = {
  today: 'Today',
  yesterday: 'Yesterday',
  custom: 'Custom Date Range',
}

/* ---- Agent-only humour. Managers never see any of this. ---- */
const QUIPS = {
  active: [
    'Currently looking busy. Convincingly.',
    'This meeting could have been a break.',
    'Hydrate or diedrate. Your call.',
    'Per my last coffee: it is almost time.',
    'Productivity at 110%. Snack levels: concerning.',
  ],
  low: [
    'Break battery low. Choose your snacks wisely.',
    'Running on fumes and good intentions.',
    'Every minute left is precious. Like the last biscuit.',
    'Pro tip: a stretch counts as a mini-break. (It does not.)',
    'Spending breaks like a startup spends runway.',
  ],
  over: [
    'Break budget exceeded. The spreadsheet misses you.',
    'Your chair is filing a missing-person report.',
    'Quietly returning to your desk is a valid strategy.',
    'We are now officially in overtime snacking.',
    'Breaking news: you have broken the break.',
  ],
  break: [
    'Out of office. Out of mind.',
    'Please mute yourself. You are on break.',
    'Circling back to snacks.',
    'Synergizing with a sandwich. Do not disturb.',
    'Your to-do list will still be here. Sadly.',
  ],
}
const WELCOME_BACK = [
  'Welcome back! Your inbox kept 47 messages warm for you.',
  'You are back! The chair missed you. Mostly.',
  'Break over. Time to look extremely busy.',
  'Welcome back, hero. The Wi-Fi survived without you.',
]
const REASON_EMOJI = { Lunch: '🍱', 'Tea Break': '🍵' }

function isoDate(date) {
  return date.toISOString().slice(0, 10)
}

function defaultFilters() {
  const today = new Date()
  return {
    preset: 'today',
    date_from: isoDate(today),
    date_to: isoDate(today),
  }
}

function minutesLabel(value) {
  const minutes = Number(value || 0)
  return `${minutes} min${minutes === 1 ? '' : 's'}`
}

function dateLabel(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

function timeLabel(value) {
  if (!value) return '-'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function applyPreset(preset) {
  const today = new Date()
  if (preset === 'yesterday') {
    today.setDate(today.getDate() - 1)
  }
  return {
    preset,
    date_from: isoDate(today),
    date_to: isoDate(today),
  }
}

const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?'
const statusOf = (breakLeft) => (breakLeft > 30 ? 'available' : breakLeft >= 0 ? 'low' : 'exceeded')
const pick = (list) => list[Math.floor(Math.random() * list.length)]

function useEscape(handler) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') handler() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handler])
}

function BreakHistoryTable({ items, emptyText = 'No breaks found for this date range.', playful = false }) {
  return (
    <div className="breakModule-table-wrap">
      <table className="breakModule-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Start Time</th>
            <th>End Time</th>
            <th>Duration (mins)</th>
            <th>Reason</th>
            {playful ? <th>Verdict</th> : null}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{dateLabel(item.start_time)}</td>
              <td>{timeLabel(item.start_time)}</td>
              <td>{item.end_time || !playful ? timeLabel(item.end_time) : <span className="breakModule-live-pill">Ongoing</span>}</td>
              <td className="breakModule-duration">{item.duration_minutes ?? 0}</td>
              <td>
                {playful
                  ? <span className="breakModule-chip"><span aria-hidden="true">{REASON_EMOJI[item.reason] || '☕'}</span>{item.reason}</span>
                  : item.reason}
              </td>
              {playful ? <td className="breakModule-verdict"><span aria-hidden="true">{verdictFor(item)[0]}</span> {verdictFor(item)[1]}</td> : null}
            </tr>
          ))}
          {!items.length ? (
            <tr>
              <td colSpan={playful ? 6 : 5}>
                <div className="breakModule-empty">
                  {playful ? <span className="breakModule-empty-emoji" aria-hidden="true">🤖</span> : null}
                  {playful ? 'No breaks logged. Either you are a machine, or you forgot to click.' : emptyText}
                </div>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function DateRangeControls({ filters, onChange }) {
  return (
    <div className="breakModule-date-controls">
      <select aria-label="Date range" value={filters.preset} onChange={(event) => onChange(applyPreset(event.target.value))}>
        {Object.entries(QUICK_RANGES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input
        type="date"
        aria-label="From date"
        value={filters.date_from}
        onChange={(event) => onChange({ ...filters, preset: 'custom', date_from: event.target.value })}
      />
      <input
        type="date"
        aria-label="To date"
        value={filters.date_to}
        onChange={(event) => onChange({ ...filters, preset: 'custom', date_to: event.target.value })}
      />
    </div>
  )
}

/* =====================  MANAGER VIEW (professional)  ===================== */

function UserBreakCard({ user, onOpen }) {
  const used = Number(user.total_break_minutes_today || 0)
  const breakLeft = DAILY_BREAK_ALLOWANCE_MINUTES - used
  const breakLeftStatus = statusOf(breakLeft)
  const percent = Math.min(100, Math.max(0, (used / DAILY_BREAK_ALLOWANCE_MINUTES) * 100))
  const stateClass = user.is_on_break ? 'on-break' : 'active'

  return (
    <button className={`breakModule-user-card ${stateClass}`} type="button" onClick={() => onOpen(user)}>
      <span className="breakModule-card-top">
        <span className="breakModule-avatar" aria-hidden="true">{initials(user.user_name)}</span>
        <strong>{user.user_name}</strong>
        <span className={`breakModule-pill ${stateClass}`}>{user.is_on_break ? 'On Break' : 'Active'}</span>
      </span>
      <span className={`breakModule-meter ${breakLeftStatus}`} role="img" aria-label={`${used} of ${DAILY_BREAK_ALLOWANCE_MINUTES} minutes used`}>
        <i style={{ width: `${percent}%` }} />
      </span>
      <span className="breakModule-card-foot">
        <span>Total Break Time: <b>{minutesLabel(used)}</b></span>
        <span className={`breakModule-break-left ${breakLeftStatus}`}><b>Break left: {minutesLabel(breakLeft)}</b></span>
      </span>
      {user.is_on_break ? <span className="breakModule-card-reason">Status: {user.active_reason || 'Break'}</span> : null}
    </button>
  )
}

function UserHistoryModal({ user, onClose }) {
  const [filters, setFilters] = useState(defaultFilters)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEscape(onClose)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetchBreakHistory({
      user_id: user.user_id,
      date_from: filters.date_from,
      date_to: filters.date_to,
    })
      .then((response) => {
        if (active) setItems(response.items || [])
      })
      .catch((caughtError) => {
        if (active) setError(caughtError.message || 'Unable to load break history.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [user.user_id, filters.date_from, filters.date_to])

  return (
    <div className="breakModule-detail-backdrop" onMouseDown={onClose}>
      <section
        className="breakModule-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Break history for ${user.user_name}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="breakModule-detail-header">
          <div>
            <span>Employee Break History Table</span>
            <h2>{user.user_name}</h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <DateRangeControls filters={filters} onChange={setFilters} />
        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading
          ? <div className="breakModule-skeleton" aria-label="Loading break history"><span /><span /><span /></div>
          : <BreakHistoryTable items={items} />}
      </section>
    </div>
  )
}

function BreakExportDialog({ onClose }) {
  const [employees, setEmployees] = useState([])
  const [selection, setSelection] = useState('all')
  const [selectedIds, setSelectedIds] = useState([])
  const [filters, setFilters] = useState(defaultFilters)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEscape(onClose)

  useEffect(() => {
    fetchBreakEmployees()
      .then((response) => setEmployees(response.items || []))
      .catch((caughtError) => setError(caughtError.message || 'Unable to load employees.'))
  }, [])

  function toggleEmployee(id) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  async function download(event) {
    event.preventDefault()
    if (filters.date_from > filters.date_to) {
      setError('Start date must be on or before end date.')
      return
    }
    if (selection === 'selected' && !selectedIds.length) {
      setError('Select at least one employee.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const blob = await exportBreakReport({
        date_from: filters.date_from,
        date_to: filters.date_to,
        user_ids: selection === 'all' ? undefined : selectedIds,
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `break_report_${filters.date_from}_${filters.date_to}.xlsx`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
      onClose()
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to export break report.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="breakModule-modal-backdrop">
      <form className="breakModule-export-modal" role="dialog" aria-modal="true" aria-label="Export break report" onSubmit={download}>
        <div className="breakModule-modal-header">
          <div><h2>Export Break Report</h2></div>
          <button type="button" aria-label="Close" onClick={onClose}><Icon name="close" /></button>
        </div>
        <fieldset className="breakModule-export-fieldset">
          <legend>Employees</legend>
          <label><input type="radio" name="employeeSelection" checked={selection === 'all'} onChange={() => setSelection('all')} /> All employees</label>
          <label><input type="radio" name="employeeSelection" checked={selection === 'selected'} onChange={() => setSelection('selected')} /> Select employees</label>
          {selection === 'selected' ? (
            <div className="breakModule-employee-list">
              {employees.map((employee) => (
                <label key={employee.id}>
                  <input type="checkbox" checked={selectedIds.includes(employee.id)} onChange={() => toggleEmployee(employee.id)} />
                  <span>{employee.name}</span><small>{employee.role.replaceAll('_', ' ')}</small>
                </label>
              ))}
              {!employees.length ? <span>No employees available.</span> : null}
            </div>
          ) : null}
        </fieldset>
        <div className="breakModule-export-dates">
          <label>From<input type="date" required value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} /></label>
          <label>To<input type="date" required value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} /></label>
        </div>
        {error ? <p className="breakModule-message error" role="alert">{error}</p> : null}
        <div className="breakModule-modal-actions">
          <button className="breakModule-secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="breakModule-primary" type="submit" disabled={busy}>{busy ? 'Preparing...' : 'Download Excel'}</button>
        </div>
      </form>
    </div>
  )
}

function ManagerBreakView() {
  const [overview, setOverview] = useState({ sections: [] })
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [exportOpen, setExportOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  async function loadOverview() {
    setLoading(true)
    setError('')
    try {
      const response = await fetchBreakOverview()
      setOverview(response)
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to load break overview.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOverview()
  }, [])

  const allUsers = useMemo(() => (overview.sections || []).flatMap((section) => section.users || []), [overview])
  const counts = useMemo(() => {
    const onBreak = allUsers.filter((user) => user.is_on_break).length
    const over = allUsers.filter((user) => Number(user.total_break_minutes_today || 0) > DAILY_BREAK_ALLOWANCE_MINUTES).length
    return { total: allUsers.length, onBreak, active: allUsers.length - onBreak, over }
  }, [allUsers])

  const visibleSections = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (overview.sections || [])
      .map((section) => ({
        ...section,
        users: (section.users || []).filter((user) => {
          if (statusFilter === 'break' && !user.is_on_break) return false
          if (statusFilter === 'active' && user.is_on_break) return false
          return !needle || String(user.user_name || '').toLowerCase().includes(needle)
        }),
      }))
      .filter((section) => section.users.length)
  }, [overview, query, statusFilter])

  return (
    <>
      <section className="breakModule-summary-band" aria-label="Today at a glance">
        <div className="breakModule-tile is-accent"><span>Employees</span><strong>{counts.total}</strong><small>Tracked today</small></div>
        <div className="breakModule-tile is-warn"><span>On break now</span><strong>{counts.onBreak}</strong><small>Currently away</small></div>
        <div className="breakModule-tile is-ok"><span>Available</span><strong>{counts.active}</strong><small>At their desk</small></div>
        <div className="breakModule-tile is-bad"><span>Over allowance</span><strong>{counts.over}</strong><small>Above {DAILY_BREAK_ALLOWANCE_MINUTES} mins today</small></div>
      </section>

      <section className="breakModule-panel breakModule-overview">
        <div className="breakModule-panel-header">
          <div>
            <h2>Employee Break Status - Today</h2>
            <p>Live role-wise break visibility for admins, ops managers, and agents.</p>
          </div>
          <div className="breakModule-header-actions">
            <button className="breakModule-secondary" type="button" onClick={() => setExportOpen(true)}>Export Excel</button>
            <button className="breakModule-secondary" type="button" onClick={loadOverview}>
              <Icon name="refresh" /> Refresh
            </button>
          </div>
        </div>

        <div className="breakModule-toolbar">
          <input
            className="breakModule-search"
            type="search"
            placeholder="Search employee..."
            aria-label="Search employee"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="breakModule-segmented" role="group" aria-label="Filter by status">
            <button type="button" aria-pressed={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>All <b>{counts.total}</b></button>
            <button type="button" aria-pressed={statusFilter === 'break'} onClick={() => setStatusFilter('break')}>On break <b>{counts.onBreak}</b></button>
            <button type="button" aria-pressed={statusFilter === 'active'} onClick={() => setStatusFilter('active')}>Active <b>{counts.active}</b></button>
          </div>
        </div>

        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading ? <div className="breakModule-skeleton" aria-label="Loading employee break status"><span /><span /><span /></div> : null}
        {!loading && visibleSections.map((section) => (
          <section className="breakModule-role-section" key={section.role_key}>
            <h3>{section.title}<small>{section.users.length}</small></h3>
            <div className="breakModule-card-grid">
              {section.users.map((user) => <UserBreakCard key={user.user_id} user={user} onOpen={setSelectedUser} />)}
            </div>
          </section>
        ))}
        {!loading && !error && !visibleSections.length ? <div className="breakModule-empty">No employees match your filters.</div> : null}
      </section>
      {selectedUser ? <UserHistoryModal user={selectedUser} onClose={() => setSelectedUser(null)} /> : null}
      {exportOpen ? <BreakExportDialog onClose={() => setExportOpen(false)} /> : null}
    </>
  )
}

/* =====================  AGENT VIEW (playful)  ===================== */

const EXCUSES = [
  'Defragmenting my brain. Please do not interrupt the progress bar.',
  'In a meeting with my sandwich. It is a hostile negotiation.',
  'My stapler has requested emotional support.',
  'Attending a webinar called “How to Stand Up Effectively”.',
  'Recalibrating my chair. It is a delicate procedure.',
  'Chasing a rogue paper clip. Strictly business.',
  'Hydration audit in progress. Findings: I am a raisin.',
  'Compliance training for my coffee mug.',
  'Escorting the Wi-Fi back to a good mood.',
  'Conducting a one-person fire drill. The fire is hunger.',
  'On a quick sync with a vending machine. It owes me a chocolate.',
  'Stretching. HR calls it “wellness”. I call it paperwork.',
]
const HEADLINES = [
  'BREAKING: Local employee discovers snacks exist',
  'Stand-up about stand-ups rescheduled to a meeting about meetings',
  'Printer once again chooses violence',
  'HR reminds everyone: the office fridge is not a time capsule',
  'Wi-Fi reportedly “fine” for everyone except you',
  'Manager’s “quick sync” now entering its fourth hour',
  'Reply-all storm expected around 4 PM',
  'Sources confirm: the last biscuit was taken by “someone”',
  'Coffee machine declared emotionally unavailable',
]
const POKE_LINES = [
  [1, 'Hey! Personal space!'],
  [3, 'I will be telling HR about this.'],
  [5, 'That is harassment. Filing a ticket.'],
  [8, 'Ticket closed: “works as intended”.'],
  [10, 'FINE. Doing a spin. Happy now?'],
]
const BREAK_STAGES = [
  [5, '🛋️ Settling in…'],
  [15, '😌 Peak relaxation achieved'],
  [30, '😴 Seriously considering a nap'],
  [45, '📝 Your desk is writing a memoir'],
  [60, '🤨 Your manager’s eyebrow has been raised'],
  [Infinity, '🚨 This is now technically a sabbatical'],
]
const BATTERY_NOTE = { available: 'Fully caffeinated', low: 'Please plug in a snack', exceeded: 'Battery dead. Running on spite.' }
const RAIN = ['🍕', '🍩', '☕', '🍪', '🍿', '🥐', '🍫', '🧁']

const pokeLine = (count) => POKE_LINES.reduce((line, [threshold, text]) => (count >= threshold ? text : line), POKE_LINES[0][1])

function verdictFor(item) {
  if (!item.end_time) return ['🌀', 'Still vibing']
  const minutes = Number(item.duration_minutes || 0)
  if (minutes < 5) return ['🥤', 'Quick sip']
  if (minutes < 15) return ['⚡', 'Tactical recharge']
  if (minutes < 30) return ['😌', 'Proper break']
  if (minutes <= 45) return ['🛋️', 'Epic hiatus']
  return ['🏖️', 'Mini sabbatical']
}

function Mascot() {
  return (
    <svg viewBox="0 0 180 180" aria-hidden="true" focusable="false">
      <ellipse cx="90" cy="173" rx="54" ry="6" fill="rgba(15,23,42,0.16)" />

      {/* body: shirt, collar, tie, badge */}
      <path className="sl-shirt" d="M34 172 Q34 128 90 122 Q146 128 146 172 Z" />
      <path className="sl-collar" d="M74 124 l16 16 l16 -16 l-7 -5 h-18 z" />
      <path className="sl-tie" d="M85 135 h10 l-2 6 h-6 z" />
      <path className="sl-tie" d="M90 140 l-7 6 l7 24 l7 -24 z" />
      <rect className="sl-badge" x="48" y="146" width="24" height="18" rx="3" />
      <rect className="sl-badge-bar" x="48" y="146" width="24" height="5" rx="2" />
      <circle className="sl-badge-dot" cx="60" cy="157" r="3" />

      {/* left arm */}
      <ellipse className="sl-fur" cx="32" cy="152" rx="12" ry="22" transform="rotate(12 32 152)" />

      {/* mug in right hand */}
      <g className="bm-steam">
        <path d="M132 132 q-5 -6 0 -11 q5 -5 0 -10" />
        <path d="M141 134 q-5 -6 0 -11 q5 -5 0 -10" />
      </g>
      <path className="sl-mug-handle" d="M150 142 h5 a7 7 0 0 1 0 14 h-5" />
      <rect className="sl-mug" x="123" y="136" width="28" height="26" rx="6" />
      <ellipse className="sl-coffee" cx="137" cy="138" rx="12" ry="3" />
      <ellipse className="sl-fur" cx="128" cy="156" rx="10" ry="9" />

      {/* head */}
      <g className="sl-head">
        <path className="sl-tuft" d="M82 38 q-5 -12 3 -16 M90 36 q0 -14 8 -16 M98 38 q5 -10 11 -8" />
        <circle className="sl-fur" cx="42" cy="62" r="9" />
        <circle className="sl-fur" cx="138" cy="62" r="9" />
        <ellipse className="sl-fur" cx="90" cy="82" rx="54" ry="46" />
        <ellipse className="sl-face" cx="90" cy="88" rx="41" ry="34" />
        <ellipse className="sl-patch" cx="66" cy="80" rx="10" ry="15" transform="rotate(22 66 80)" />
        <ellipse className="sl-patch" cx="114" cy="80" rx="10" ry="15" transform="rotate(-22 114 80)" />

        <g className="sl-eyes">
          <circle className="sl-eyewhite" cx="66" cy="80" r="6" />
          <circle className="sl-eyewhite" cx="114" cy="80" r="6" />
          <circle className="sl-pupil" cx="66" cy="80" r="3.2" />
          <circle className="sl-pupil" cx="114" cy="80" r="3.2" />
          <rect className="sl-lid" x="58" y="72" width="16" height="8" />
          <rect className="sl-lid" x="106" y="72" width="16" height="8" />
        </g>
        <g className="sl-closed">
          <path d="M58 81 q8 7 16 0" />
          <path d="M106 81 q8 7 16 0" />
        </g>
        <g className="sl-brows">
          <path d="M54 70 L77 62" />
          <path d="M126 70 L103 62" />
        </g>

        <ellipse className="sl-cheek" cx="55" cy="101" rx="7" ry="4.5" />
        <ellipse className="sl-cheek" cx="125" cy="101" rx="7" ry="4.5" />
        <ellipse className="sl-nose" cx="90" cy="96" rx="8" ry="5.5" />
        <ellipse className="sl-shine" cx="87" cy="94" rx="2.5" ry="1.4" />
        <circle className="sl-snot" cx="98" cy="99" r="7" />

        <path className="sl-mouth sl-mouth-smile" d="M79 106 q11 10 22 0" />
        <path className="sl-mouth sl-mouth-worry" d="M78 113 q6 -7 12 0 q6 7 12 0" />
        <g className="sl-mouth-open"><ellipse cx="90" cy="112" rx="8" ry="7" /><ellipse cx="90" cy="116" rx="4.5" ry="2.6" fill="#f87171" /></g>
        <path className="sl-sweat" d="M140 58 q-7 11 0 16 q7 -5 0 -16z" />
      </g>
    </svg>
  )
}

function useElapsed(since) {
  const start = since ? new Date(since).getTime() : NaN
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (Number.isNaN(start)) return undefined
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [start])
  return Number.isNaN(start) ? null : Math.max(0, Math.floor((now - start) / 1000))
}

function clock(totalSeconds) {
  const pad = (n) => String(n).padStart(2, '0')
  const hours = Math.floor(totalSeconds / 3600)
  return `${hours ? `${hours}:` : ''}${pad(Math.floor((totalSeconds % 3600) / 60))}:${pad(totalSeconds % 60)}`
}

function Typewriter({ text }) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setCount(text.length)
      return undefined
    }
    setCount(0)
    const id = window.setInterval(() => {
      setCount((value) => {
        if (value >= text.length) {
          window.clearInterval(id)
          return value
        }
        return value + 1
      })
    }, 26)
    return () => window.clearInterval(id)
  }, [text])
  return <>{text.slice(0, count)}<span className="breakModule-caret" aria-hidden="true" /></>
}

function Confetti({ center = false }) {
  return (
    <span className={`breakModule-confetti${center ? ' is-center' : ''}`} aria-hidden="true">
      {Array.from({ length: 18 }, (_, i) => (
        <i key={i} style={{ '--dx': `${((i * 47) % 260) - 130}px`, '--dy': `${-(70 + ((i * 61) % 150))}px`, '--rot': `${(i * 113) % 720}deg` }} />
      ))}
    </span>
  )
}

function AgentHero({ status, breakLeft, onStatusChange }) {
  const onBreak = Boolean(status.is_on_break)
  const mode = onBreak ? 'break' : breakLeft === null ? 'active' : breakLeft < 0 ? 'over' : breakLeft <= 30 ? 'low' : 'active'
  const elapsed = useElapsed(onBreak ? status.active_break?.start_time : null)
  const [index, setIndex] = useState(() => Math.floor(Math.random() * 5))
  const [pokes, setPokes] = useState(0)
  const [shout, setShout] = useState('')
  const [boop, setBoop] = useState('')
  const [party, setParty] = useState(0)
  const [excuse, setExcuse] = useState('')
  const shoutTimer = useRef(0)

  useEffect(() => {
    const id = window.setInterval(() => setIndex((value) => value + 1), 9000)
    return () => {
      window.clearInterval(id)
      window.clearTimeout(shoutTimer.current)
    }
  }, [])

  function poke() {
    const next = pokes + 1
    const spin = next % 10 === 0
    setPokes(next)
    setIndex((value) => value + 1)
    setShout(pokeLine(next))
    setBoop(spin ? 'spin' : 'boop')
    if (spin) setParty(Date.now())
    window.clearTimeout(shoutTimer.current)
    shoutTimer.current = window.setTimeout(() => { setShout(''); setBoop('') }, spin ? 3800 : 3200)
  }

  const quips = QUIPS[mode]
  const text = shout || quips[index % quips.length]
  const reason = status.active_break?.reason
  const title = {
    break: `On break${reason ? ` · ${reason}` : ''}`,
    over: 'Break budget: exceeded 🚨',
    low: 'Break battery running low',
    active: 'Clocked in and mostly caffeinated',
  }[mode]
  const stage = elapsed === null ? null : BREAK_STAGES.find(([limit]) => elapsed / 60 < limit)[1]
  const classes = `breakModule-hero${onBreak ? ' is-on-break' : ''}${mode === 'over' ? ' is-over' : ''}${mode === 'low' ? ' is-low' : ''}`

  return (
    <section className={classes} aria-label="Your break status">
      <div className="breakModule-floaters" aria-hidden="true"><span>🍩</span><span>📎</span><span>☕</span><span>💤</span><span>📈</span></div>
      {onBreak ? (
        <div className="breakModule-rain" aria-hidden="true">
          {RAIN.map((emoji, i) => <span key={emoji} style={{ left: `${5 + i * 12}%`, animationDelay: `${-i * 1.1}s` }}>{emoji}</span>)}
        </div>
      ) : null}

      <div className="breakModule-mascot-wrap">
        <button type="button" className={`breakModule-mascot${boop ? ` is-${boop}` : ''}`} onClick={poke} aria-label="Poke the mug">
          <Mascot />
          <span className="breakModule-zzz" aria-hidden="true"><span>Z</span><span>z</span><span>z</span></span>
        </button>
        {party ? <Confetti key={party} center /> : null}
        <span className="breakModule-poke-hint">{pokes ? `Pokes: ${pokes}` : '👆 poke me'}</span>
      </div>

      <div className="breakModule-hero-copy">
        <span className="breakModule-hero-pill">{onBreak ? 'On break' : mode === 'over' ? 'Over budget' : 'Active'}</span>
        <h2>{title}</h2>
        <p className="breakModule-bubble" role="status" aria-label={text}><Typewriter text={text} /></p>
        {onBreak && elapsed !== null ? (
          <div className="breakModule-timer-row">
            <div className="breakModule-timer" role="timer" aria-label="Time on current break"><span aria-hidden="true">⏱</span>{clock(elapsed)}</div>
            <span className="breakModule-stage" key={stage}>{stage}</span>
          </div>
        ) : null}
        <div className="breakModule-cta">
          <BreakActionButton playful className="is-hero" onStatusChange={onStatusChange} />
          <button type="button" className="breakModule-secondary" onClick={() => setExcuse(pick(EXCUSES.filter((item) => item !== excuse)))}>
            <span aria-hidden="true">🎲</span> Boss-proof excuse
          </button>
        </div>
        {excuse ? <p className="breakModule-excuse" key={excuse}><b>📝 Official excuse:</b> {excuse}</p> : null}
      </div>
    </section>
  )
}

function NewsTicker() {
  return (
    <div className="breakModule-ticker" aria-label="Office news ticker (jokes)">
      <span className="breakModule-ticker-label">BREAKING</span>
      <div className="breakModule-ticker-view">
        <div className="breakModule-ticker-track" aria-hidden="true">
          {[...HEADLINES, ...HEADLINES].map((headline, i) => <span key={i}>{headline}</span>)}
        </div>
      </div>
    </div>
  )
}

function WelcomeBackToast({ onDone }) {
  const [message] = useState(() => pick(WELCOME_BACK))
  useEffect(() => {
    const id = window.setTimeout(onDone, 5200)
    return () => window.clearTimeout(id)
  }, [])
  return (
    <div className="breakModule-toast-wrap" role="status">
      <div className="breakModule-toast">
        <Confetti />
        <span aria-hidden="true">🎉</span>
        <span>{message}</span>
      </div>
    </div>
  )
}

function AgentBreakView({ status, version, onStatusChange }) {
  const [filters, setFilters] = useState(defaultFilters)
  const [items, setItems] = useState([])
  const [todayMinutes, setTodayMinutes] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setTodayMinutes(null)
    const today = isoDate(new Date())
    const historyRequest = fetchBreakHistory({ date_from: filters.date_from, date_to: filters.date_to })
    const todayRequest = filters.date_from === today && filters.date_to === today
      ? historyRequest
      : fetchBreakHistory({ date_from: today, date_to: today })

    Promise.all([historyRequest, todayRequest])
      .then(([response, todayResponse]) => {
        if (active) {
          setItems(response.items || [])
          setTodayMinutes((todayResponse.items || []).reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0))
        }
      })
      .catch((caughtError) => {
        if (active) setError(caughtError.message || 'Unable to load your break history.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [filters.date_from, filters.date_to, version])

  const totalMinutes = useMemo(() => items.reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0), [items])
  const breakLeft = todayMinutes === null ? null : DAILY_BREAK_ALLOWANCE_MINUTES - todayMinutes
  const breakLeftStatus = breakLeft === null ? '' : statusOf(breakLeft)
  const leftPercent = breakLeft === null ? 0 : Math.min(100, Math.max(0, (breakLeft / DAILY_BREAK_ALLOWANCE_MINUTES) * 100))
  const breaksNote = items.length === 0 ? 'Suspiciously dedicated' : items.length <= 2 ? 'Healthy balance' : 'Snack enthusiast'

  return (
    <>
      <AgentHero status={status} breakLeft={breakLeft} onStatusChange={onStatusChange} />
      <NewsTicker />
      <section className="breakModule-summary-band">
        <div className="breakModule-tile is-accent">
          <span>Breaks in range</span>
          <strong>{items.length}</strong>
          <small>{breaksNote}</small>
        </div>
        <div className="breakModule-tile is-accent">
          <span>Total duration</span>
          <strong>{minutesLabel(totalMinutes)}</strong>
          <small>Time well wasted</small>
        </div>
        <div className={`breakModule-tile ${breakLeftStatus === 'available' ? 'is-ok' : breakLeftStatus === 'low' ? 'is-warn' : breakLeftStatus === 'exceeded' ? 'is-bad' : ''}`}>
          <span>Break left today</span>
          <strong className={`breakModule-break-left is-big ${breakLeftStatus}`}>{breakLeft === null ? '—' : minutesLabel(breakLeft)}</strong>
          <div className={`breakModule-battery ${breakLeftStatus}`} role="img" aria-label="Break time remaining">
            <div className="breakModule-battery-body"><i style={{ width: `${leftPercent}%` }} /></div>
            <span className="breakModule-battery-nub" />
          </div>
          <small>{BATTERY_NOTE[breakLeftStatus] || 'Checking the biscuit tin...'}</small>
        </div>
      </section>
      <section className="breakModule-panel">
        <div className="breakModule-panel-header">
          <div>
            <h2>Personal Break History</h2>
            <p>Daily break entries and reasons from your audit trail. Each one gets an official verdict.</p>
          </div>
          <DateRangeControls filters={filters} onChange={setFilters} />
        </div>
        {error ? <p className="breakModule-message error">{error}</p> : null}
        {loading
          ? <div className="breakModule-skeleton" aria-label="Loading break history"><span /><span /><span /></div>
          : <BreakHistoryTable items={items} playful />}
      </section>
    </>
  )
}

/* =====================  PAGE  ===================== */

/* Fit the page to the space under the app's top bar and lock window scrolling while mounted,
   so only the break content scrolls (the sidebar and top bar stay put). */
function useFitViewport(ref) {
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const html = document.documentElement
    const previous = { html: html.style.overflow, body: document.body.style.overflow }

    function fit() {
      window.scrollTo(0, 0)
      for (let node = el.parentElement; node; node = node.parentElement) {
        if (node.scrollTop) node.scrollTop = 0
      }
      el.style.height = 'auto'
      const top = el.getBoundingClientRect().top
      el.style.height = `${Math.max(320, window.innerHeight - Math.max(0, top))}px`
    }

    html.style.overflow = 'hidden'
    document.body.style.overflow = 'hidden'
    fit()
    window.addEventListener('resize', fit)
    return () => {
      window.removeEventListener('resize', fit)
      html.style.overflow = previous.html
      document.body.style.overflow = previous.body
      el.style.height = ''
    }
  }, [ref])
}

function BreakManagement({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role)
  const isManagerView = ['ADMIN', 'OPS_MANAGER'].includes(role)

  const pageRef = useRef(null)
  useFitViewport(pageRef)

  const [breakStatus, setBreakStatus] = useState({ is_on_break: false, active_break: null })
  const [breakVersion, setBreakVersion] = useState(0)
  const [welcomeBack, setWelcomeBack] = useState(null)
  const previousOnBreak = useRef(null)
  const isManagerRef = useRef(isManagerView)
  isManagerRef.current = isManagerView

  const handleStatusChange = useCallback((next) => {
    const now = Boolean(next?.is_on_break)
    const previous = previousOnBreak.current
    previousOnBreak.current = now
    setBreakStatus(next)
    if (previous !== null && previous !== now) {
      setBreakVersion((value) => value + 1)
      if (previous && !now && !isManagerRef.current) setWelcomeBack(Date.now())
    }
  }, [])

  return (
    <AppLayout activePage="Breaks" currentUser={currentUser} onLogout={onLogout}>
      <main className="breakModule-page" ref={pageRef}>
        <header className="breakModule-header">
          <div>
            <span>Workforce Operations</span>
            <h1>Break Management</h1>
            <p>
              {isManagerView
                ? 'Track break status, durations, reasons, and immutable start/end audit events.'
                : 'Recharge responsibly. Breaks are logged, snacks are not.'}
            </p>
          </div>
          {isManagerView ? <BreakActionButton /> : null}
        </header>
        {isManagerView
          ? <ManagerBreakView />
          : <AgentBreakView status={breakStatus} version={breakVersion} onStatusChange={handleStatusChange} />}
        {welcomeBack ? <WelcomeBackToast key={welcomeBack} onDone={() => setWelcomeBack(null)} /> : null}
      </main>
    </AppLayout>
  )
}

export default BreakManagement
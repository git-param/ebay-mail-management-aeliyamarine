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

function buildLeaveEmailTemplate(form, policy, managerName = '') {
  const details = leaveEmailDetails(form, policy)
  const date = leaveDateText(form)
  const leaveType = form.leave_type === 'PAID' && form.day_part === 'FULL' && form.end_date && form.end_date !== form.start_date
    ? 'Full Day Leaves'
    : details.type
  const reason = form.reason.trim() || '[reason - optional]'
  const greetingName = managerName.trim() || '[Manager\'s Name / Team]'

  return [
    `Subject: ${leaveType} (${details.time}) - ${date}`,
    '',
    `Dear ${greetingName},`,
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

const HERO_COPY = {
  tired: {
    emoji: '😴',
    title: 'Running on 3% battery and 5 coffees',
    text: 'Back-to-back tickets, calls that “will only take a minute”, and a headset-shaped dent in your head. Pick a date below. You have earned it.',
    jokes: [
      'This leave request could have been an email. So could my last 14 meetings.',
      'My AHT is great. My will to live is on hold.',
      'Please hold. I am also on hold. With myself.',
      'Customer said “quick question”. 47 minutes ago.',
      'I am not tired. I am buffering.',
    ],
    thoughts: [
      'Just five more minutes… of ten more hours.',
      'Is it Friday yet? (it is not)',
      'My coffee has a coffee. 🫠',
      'Why is “urgent” always at 6:25 PM?',
      'Zzz… no, I am listening. Continue.',
    ],
    pokes: [
      'Ow! Is that a new ticket?!',
      'I am awake! I am awake! 👀',
      'Please do not wake me. Unless it is leave.',
      'I was on mute. Always on mute.',
    ],
    feed: [
      ['💬', 'Teams: “Got a minute?” (it is never a minute)'],
      ['📧', '“Per my last email…”'],
      ['🔔', '47 unread. It is only Monday.'],
    ],
  },
  excited: {
    emoji: '🎉',
    title: 'Dates picked. Hope has been restored.',
    text: 'Look at that spark! Fill in the details, copy the email, and hit submit before another “urgent” ping arrives.',
    jokes: [
      'Calendar: blocked. Laptop: closing. Soul: leaving.',
      'Mentally, I have already left the building.',
      'Typing “OOO” has never felt so good.',
      'Packing list: charger, sunscreen, zero responsibilities.',
      'Somewhere a beach just got slightly more crowded.',
    ],
    thoughts: [
      'Beach? Mountains? Bed? YES.',
      'Adios, standups! 👋',
      'I have already muted every group.',
      'Out-of-office reply: drafted since 2024.',
      'Leave form? I will fill it in 3 seconds.',
    ],
    pokes: [
      'Wheee! 🎉',
      'Do not touch my leave! (touch it more)',
      'I can feel the sunscreen already.',
      'Tickets? Never heard of her.',
    ],
    feed: [
      ['✈️', 'Auto-reply: “Gone. Do not reply.”'],
      ['🧳', 'Packing: 0%. Vibes: 100%.'],
      ['🔒', 'Calendar: blocked. Do not book.'],
    ],
  },
  sweating: {
    emoji: '😰',
    title: 'Pending… refreshing nervously',
    text: 'Your request is waiting for approval. The admin is probably in a meeting about meetings. Breathe.',
    jokes: [
      'Staring at the status badge will not approve it faster. Probably.',
      '“Pending” is just corporate for “maybe”.',
      'I have checked this page 14 times. It is fine. I am fine.',
      'Sweating more than the office AC can handle.',
      'Approve me like you approve lunch breaks: quickly.',
    ],
    thoughts: [
      'Did they see it? Did they SEE it?!',
      'Admin is online. Admin is NOT replying.',
      'Refresh. Refresh. Refresh. Refresh.',
      'What if they say no? What if they say… maybe?',
      'Typing… stop typing… typing…',
    ],
    pokes: [
      'Do not poke me, I am fragile!',
      'I am calm. (not calm)',
      'Is that an approval?! …no. 😭',
      '*nervous clicking intensifies*',
    ],
    feed: [
      ['⏳', 'Status: pending… (day 1)'],
      ['🔄', 'Refreshed again. Nothing.'],
      ['👀', 'Admin is “typing…”'],
    ],
  },
  beach: {
    emoji: '🏖️',
    title: 'Approved! Out of office, out of mind',
    text: 'Close the laptop, silence the notifications, and let the ticket queue sort itself out.',
    jokes: [
      'Deadlines have been left on read.',
      'Slack status: sand-level connectivity only.',
      'Tie: removed. Sunglasses: on. Worries: offline.',
      'Out of office. Into the ocean.',
      'Customer escalations? Please talk to the crab.',
    ],
    thoughts: [
      'Ticket queue? Never heard of her.',
      'This is fine. This is very fine. 🏖️',
      'My phone says 47 unread. My phone is wrong.',
      'Sunscreen? Done. Tie? Gone.',
      'Reply-all? Reply-never.',
    ],
    pokes: [
      'Shh, I am on a very important break.',
      'Do not ping me, I am on crab time.',
      'Is that a notification? No, a wave.',
      'Cheers! 🍹',
    ],
    feed: [
      ['📵', '47 unread. Ignored with love.'],
      ['🍹', 'Hydration: coconut.'],
      ['🦀', 'Crab: “not my ticket”.'],
    ],
  },
}

const CONFETTI = Array.from({ length: 18 }, (_, index) => ({
  x: 12 + ((index * 47) % 396),
  delay: (index % 9) * 0.35,
  size: 5 + (index % 3) * 2,
  color: ['#fbbf24', '#a78bfa', '#34d399', '#fb7185', '#38bdf8'][index % 5],
}))

function LeaveWorker({ mood }) {
  const skin = '#f2c9a5'
  const beach = mood === 'beach'
  const shirt = beach ? '#f59e0b' : '#44537f'

  return (
    <g className="leaveHero-worker">
      <g className="leaveHero-body">
        <path d="M58 200 Q60 142 96 130 L144 130 Q180 142 182 200 Z" fill={shirt} />
        {beach ? (
          <g fill="#fff" opacity="0.85">
            <circle cx="84" cy="164" r="4" />
            <circle cx="156" cy="170" r="4" />
            <circle cx="120" cy="184" r="4" />
            <circle cx="100" cy="150" r="3" />
            <circle cx="142" cy="152" r="3" />
          </g>
        ) : (
          <g>
            <path d="M102 130 L120 154 L138 130 Z" fill="#f8fafc" />
            <path d="M116 150 L124 150 L128 178 L120 188 L112 178 Z" fill="#c0392b" />
            <rect x="146" y="158" width="16" height="20" rx="2" fill="#f8fafc" stroke="#94a3b8" strokeWidth="1" />
            <circle cx="154" cy="165" r="3" fill="#94a3b8" />
          </g>
        )}
        <rect x="110" y="112" width="20" height="22" rx="6" fill={skin} />
      </g>

      <g className="leaveHero-head">
        <circle cx="120" cy="86" r="34" fill={skin} />
        <path d="M85 80 Q86 48 120 46 Q154 48 155 80 Q142 62 120 62 Q98 62 85 80 Z" fill="#3b2a20" />
        {mood === 'tired' ? (
          <path className="leaveHero-strand" d="M118 48 Q110 34 124 28" stroke="#3b2a20" strokeWidth="3" fill="none" strokeLinecap="round" />
        ) : null}

        {!beach ? (
          <g>
            <path d="M87 82 Q88 38 120 38 Q152 38 153 82" stroke="#334155" strokeWidth="4" fill="none" strokeLinecap="round" />
            <rect x="82" y="78" width="9" height="18" rx="4" fill="#334155" />
            <rect x="149" y="78" width="9" height="18" rx="4" fill="#334155" />
            <path d="M86 94 Q88 112 104 110" stroke="#334155" strokeWidth="2.4" fill="none" strokeLinecap="round" />
            <circle cx="105" cy="110" r="3.2" fill="#334155" />
          </g>
        ) : null}

        {mood === 'tired' ? (
          <g>
            <circle cx="106" cy="86" r="6" fill="#fff" />
            <circle cx="134" cy="86" r="6" fill="#fff" />
            <circle cx="106" cy="88" r="2.6" fill="#1f2937" />
            <circle cx="134" cy="88" r="2.6" fill="#1f2937" />
            <rect x="98" y="78" width="16" height="9" fill={skin} />
            <rect x="126" y="78" width="16" height="9" fill={skin} />
            <path d="M98 87 H114 M126 87 H142" stroke="#3b2a20" strokeWidth="2" strokeLinecap="round" />
            <path d="M100 95 Q106 99 112 95 M128 95 Q134 99 140 95" stroke="#8b5e83" strokeWidth="2" fill="none" strokeLinecap="round" />
            <ellipse className="leaveHero-yawn" cx="122" cy="108" rx="6" ry="5" fill="#7f1d1d" />
          </g>
        ) : null}

        {mood === 'excited' ? (
          <g>
            <circle cx="106" cy="84" r="7" fill="#fff" />
            <circle cx="134" cy="84" r="7" fill="#fff" />
            <circle cx="107" cy="84" r="3.4" fill="#1f2937" />
            <circle cx="135" cy="84" r="3.4" fill="#1f2937" />
            <circle cx="108" cy="82.6" r="1.1" fill="#fff" />
            <circle cx="136" cy="82.6" r="1.1" fill="#fff" />
            <path d="M97 70 Q106 64 115 70 M125 70 Q134 64 143 70" stroke="#3b2a20" strokeWidth="2.4" fill="none" strokeLinecap="round" />
            <path d="M104 98 Q122 122 140 98 Z" fill="#fff" stroke="#7f1d1d" strokeWidth="2" strokeLinejoin="round" />
            <circle cx="96" cy="98" r="5" fill="#fb7185" opacity="0.4" />
            <circle cx="146" cy="98" r="5" fill="#fb7185" opacity="0.4" />
          </g>
        ) : null}

        {mood === 'sweating' ? (
          <g>
            <circle cx="106" cy="86" r="6" fill="#fff" />
            <circle cx="134" cy="86" r="6" fill="#fff" />
            <circle cx="108" cy="87" r="2" fill="#1f2937" />
            <circle cx="132" cy="87" r="2" fill="#1f2937" />
            <path d="M97 74 L114 69 M143 74 L126 69" stroke="#3b2a20" strokeWidth="2.4" strokeLinecap="round" />
            <path d="M110 106 q4 -5 8 0 t8 0 t8 0" stroke="#7f1d1d" strokeWidth="2.2" fill="none" strokeLinecap="round" />
            <path className="leaveHero-drop leaveHero-drop-a" d="M158 70 Q164 80 158 86 Q152 80 158 70 Z" fill="#38bdf8" />
            <path className="leaveHero-drop leaveHero-drop-b" d="M82 62 Q88 72 82 78 Q76 72 82 62 Z" fill="#38bdf8" />
            <path className="leaveHero-drop leaveHero-drop-c" d="M150 50 Q155 58 150 63 Q145 58 150 50 Z" fill="#38bdf8" />
          </g>
        ) : null}

        {beach ? (
          <g>
            <rect x="94" y="78" width="24" height="15" rx="6" fill="#111827" />
            <rect x="122" y="78" width="24" height="15" rx="6" fill="#111827" />
            <path d="M118 84 H122" stroke="#111827" strokeWidth="3" />
            <path d="M94 82 L86 80 M146 82 L154 80" stroke="#111827" strokeWidth="2.4" strokeLinecap="round" />
            <path d="M99 82 L104 82 M127 82 L132 82" stroke="#fff" strokeWidth="1.6" opacity="0.5" strokeLinecap="round" />
            <path d="M104 100 Q120 116 136 100" stroke="#7f1d1d" strokeWidth="2.4" fill="none" strokeLinecap="round" />
          </g>
        ) : null}
      </g>

      {mood === 'excited' ? (
        <g>
          <g>
            <animateTransform attributeName="transform" type="rotate" values="-14 98 142;14 98 142;-14 98 142" dur="0.6s" repeatCount="indefinite" />
            <line x1="98" y1="142" x2="62" y2="96" stroke={shirt} strokeWidth="14" strokeLinecap="round" />
            <circle cx="60" cy="92" r="7" fill={skin} />
          </g>
          <g>
            <animateTransform attributeName="transform" type="rotate" values="14 142 142;-14 142 142;14 142 142" dur="0.6s" repeatCount="indefinite" />
            <line x1="142" y1="142" x2="178" y2="96" stroke={shirt} strokeWidth="14" strokeLinecap="round" />
            <circle cx="180" cy="92" r="7" fill={skin} />
          </g>
        </g>
      ) : null}

      {mood === 'sweating' ? (
        <g>
          <path d="M98 146 L72 130 L94 106" stroke={shirt} strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          <circle cx="96" cy="102" r="7" fill={skin} />
          <path d="M142 146 L168 130 L146 106" stroke={shirt} strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          <circle cx="144" cy="102" r="7" fill={skin} />
        </g>
      ) : null}

      {beach ? (
        <g>
          <line x1="98" y1="144" x2="80" y2="176" stroke={shirt} strokeWidth="14" strokeLinecap="round" />
          <circle cx="78" cy="180" r="7" fill={skin} />
          <g>
            <animateTransform attributeName="transform" type="rotate" values="-4 142 144;6 142 144;-4 142 144" dur="2.4s" repeatCount="indefinite" />
            <line x1="142" y1="144" x2="170" y2="120" stroke={shirt} strokeWidth="14" strokeLinecap="round" />
            <circle cx="172" cy="116" r="7" fill={skin} />
            <path d="M162 90 L184 90 L178 116 L168 116 Z" fill="#fb923c" stroke="#fff" strokeWidth="1.5" />
            <path d="M176 90 L184 76" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" />
            <path d="M158 80 Q173 66 188 80 Z" fill="#a78bfa" transform="translate(0 -2)" />
          </g>
        </g>
      ) : null}
    </g>
  )
}

function Desk() {
  return (
    <g>
      <rect x="16" y="178" width="388" height="10" rx="4" fill="#a16207" />
      <rect x="28" y="188" width="364" height="52" fill="#854d0e" opacity="0.92" />
      <rect x="176" y="172" width="64" height="6" rx="2" fill="#cbd5e1" />
      <rect className="leaveHero-key" x="182" y="173" width="8" height="3" rx="1" fill="#fff" />
      <rect className="leaveHero-key leaveHero-key-b" x="196" y="173" width="8" height="3" rx="1" fill="#fff" />
      <rect className="leaveHero-key leaveHero-key-c" x="210" y="173" width="8" height="3" rx="1" fill="#fff" />
    </g>
  )
}

function Monitor({ children }) {
  return (
    <g>
      <rect x="334" y="164" width="14" height="14" fill="#64748b" />
      <rect x="318" y="174" width="46" height="5" rx="2" fill="#64748b" />
      <rect x="290" y="106" width="104" height="62" rx="6" fill="#1e293b" />
      <rect x="297" y="112" width="90" height="50" rx="3" fill="#0f172a" />
      {children}
    </g>
  )
}

function SceneBack({ mood }) {
  if (mood === 'beach') {
    const rays = Array.from({ length: 8 }, (_, index) => {
      const angle = (index * Math.PI) / 4
      return (
        <line
          key={index}
          x1={352 + 26 * Math.cos(angle)}
          y1={50 + 26 * Math.sin(angle)}
          x2={352 + 35 * Math.cos(angle)}
          y2={50 + 35 * Math.sin(angle)}
        />
      )
    })

    return (
      <g>
        <defs>
          <clipPath id="leaveHeroStageClip">
            <rect x="0" y="0" width="420" height="240" />
          </clipPath>
        </defs>
        <g clipPath="url(#leaveHeroStageClip)">
          <g>
            <circle cx="352" cy="50" r="20" fill="#fbbf24" />
            <g stroke="#fbbf24" strokeWidth="3" strokeLinecap="round">
              <animateTransform attributeName="transform" type="rotate" from="0 352 50" to="360 352 50" dur="18s" repeatCount="indefinite" />
              {rays}
            </g>
          </g>
          <g className="leaveHero-cloud">
            <ellipse cx="70" cy="46" rx="28" ry="10" fill="#fff" opacity="0.85" />
            <ellipse cx="90" cy="38" rx="17" ry="10" fill="#fff" opacity="0.85" />
          </g>
          <rect x="0" y="150" width="420" height="44" fill="#38bdf8" opacity="0.55" />
          <path
            className="leaveHero-wave"
            d="M-80 158 Q-60 150 -40 158 T0 158 T40 158 T80 158 T120 158 T160 158 T200 158 T240 158 T280 158 T320 158 T360 158 T400 158 T440 158 T480 158 V172 H-80 Z"
            fill="#7dd3fc"
            opacity="0.85"
          />
          <rect x="0" y="190" width="420" height="50" fill="#fde68a" />
          <line x1="62" y1="104" x2="62" y2="212" stroke="#92400e" strokeWidth="4" strokeLinecap="round" />
          <g className="leaveHero-wobble">
            <path d="M20 108 Q62 56 104 108 Z" fill="#ef4444" />
            <path d="M40 84 Q62 62 84 84 L74 108 L50 108 Z" fill="#fff" opacity="0.92" />
          </g>
          <g transform="translate(0 86)">
            <g className="leaveHero-gull">
              <path d="M0 0 Q7 -8 14 0 Q21 -8 28 0" fill="none" stroke="#475569" strokeWidth="2" strokeLinecap="round" />
            </g>
          </g>
        </g>
      </g>
    )
  }

  if (mood === 'excited') {
    const flags = ['#fb7185', '#fbbf24', '#34d399', '#38bdf8', '#a78bfa']
    return (
      <g>
        <rect x="0" y="212" width="420" height="28" fill="rgba(100, 116, 139, 0.16)" />
        <g className="leaveHero-sway">
          <line x1="0" y1="10" x2="420" y2="10" stroke="#94a3b8" strokeWidth="1.5" />
          {Array.from({ length: 12 }, (_, index) => (
            <path key={index} d={`M${12 + index * 36} 10 h14 l-7 15 Z`} fill={flags[index % flags.length]} />
          ))}
        </g>
        <rect x="24" y="34" width="72" height="62" rx="6" fill="#fff" stroke="#cbd5e1" strokeWidth="2" />
        <rect x="24" y="34" width="72" height="14" rx="6" fill="#ef4444" />
        <text x="60" y="45" textAnchor="middle" fontSize="8" fontWeight="900" fill="#fff">LEAVE DAY</text>
        {Array.from({ length: 15 }, (_, index) => (
          <circle key={index} cx={36 + (index % 5) * 12} cy={60 + Math.floor(index / 5) * 12} r="2.2" fill="#cbd5e1" />
        ))}
        <path d="M33 57 l6 6 M39 57 l-6 6 M45 57 l6 6 M51 57 l-6 6" stroke="#ef4444" strokeWidth="1.6" strokeLinecap="round" />
        <circle className="leaveHero-pulse" cx="72" cy="72" r="8" fill="none" stroke="#ef4444" strokeWidth="2" />
        <rect x="332" y="34" width="66" height="54" rx="4" fill="#bae6fd" stroke="#fff" strokeWidth="3" />
        <circle cx="380" cy="50" r="7" fill="#fbbf24" />
        <path d="M332 72 Q346 64 360 72 T398 72 V88 H332 Z" fill="#38bdf8" />
        <text x="365" y="84" textAnchor="middle" fontSize="9" fontWeight="900" fill="#fff">SOON™</text>
      </g>
    )
  }

  const fast = mood === 'sweating'
  return (
    <g>
      <rect x="0" y="212" width="420" height="28" fill="rgba(100, 116, 139, 0.16)" />
      <circle cx="50" cy="52" r="24" fill="#fff" stroke="#94a3b8" strokeWidth="3" />
      <line x1="50" y1="52" x2="50" y2="36" stroke="#475569" strokeWidth="2.4" strokeLinecap="round">
        <animateTransform attributeName="transform" type="rotate" from={fast ? '0 50 52' : '0 50 52'} to={fast ? '360 50 52' : '-360 50 52'} dur={fast ? '1.2s' : '16s'} repeatCount="indefinite" />
      </line>
      <line x1="50" y1="52" x2="61" y2="58" stroke="#475569" strokeWidth="3" strokeLinecap="round">
        {fast ? <animateTransform attributeName="transform" type="rotate" from="0 50 52" to="360 50 52" dur="8s" repeatCount="indefinite" /> : null}
      </line>
      <circle cx="50" cy="52" r="2.4" fill="#475569" />
      <text x="50" y="90" textAnchor="middle" fontSize="9" fontWeight="800" fill="#64748b">{fast ? 'any day now' : 'still 6:29 PM'}</text>
      {fast ? (
        <g transform="rotate(-10 364 56)">
          <g className="leaveHero-pulse">
            <rect x="322" y="40" width="84" height="32" rx="4" fill="none" stroke="#ef4444" strokeWidth="3" />
            <text x="364" y="61" textAnchor="middle" fontSize="15" fontWeight="900" fill="#ef4444">PENDING</text>
          </g>
        </g>
      ) : (
        <g>
          <rect x="332" y="28" width="66" height="60" rx="6" fill="#fff" stroke="#cbd5e1" strokeWidth="2" />
          <rect x="332" y="28" width="66" height="16" rx="6" fill="#ef4444" />
          <text x="365" y="40" textAnchor="middle" fontSize="9" fontWeight="900" fill="#fff">MONDAY</text>
          <text x="365" y="70" textAnchor="middle" fontSize="11" fontWeight="800" fill="#334155">(again)</text>
        </g>
      )}
    </g>
  )
}

function SceneFront({ mood, refreshes }) {
  if (mood === 'tired') {
    return (
      <g>
        <Desk />
        <Monitor>
          <rect x="303" y="122" width="50" height="4" fill="#38bdf8" opacity="0.6" />
          <rect x="303" y="132" width="36" height="4" fill="#38bdf8" opacity="0.6" />
          <rect x="303" y="142" width="44" height="4" fill="#38bdf8" opacity="0.6" />
          <rect className="leaveHero-blink" x="303" y="150" width="6" height="8" fill="#e2e8f0" />
          <circle className="leaveHero-pulse" cx="372" cy="140" r="11" fill="#ef4444" />
          <text x="372" y="144" textAnchor="middle" fontSize="10" fontWeight="900" fill="#fff">47</text>
        </Monitor>
        <g transform="rotate(8 394 104)">
          <g className="leaveHero-wiggle">
            <rect x="380" y="90" width="28" height="22" fill="#fde047" />
            <text x="394" y="104" textAnchor="middle" fontSize="8" fontWeight="900" fill="#854d0e">TODO</text>
          </g>
        </g>
        {[44, 68].map((x) => (
          <g key={x}>
            <rect x={x} y="158" width="18" height="20" rx="3" fill="#fff" stroke="#cbd5e1" />
            <rect x={x} y="164" width="18" height="5" fill="#92400e" opacity="0.45" />
          </g>
        ))}
        <rect x="92" y="158" width="18" height="20" rx="3" fill="#fff" stroke="#cbd5e1" />
        <rect x="92" y="164" width="18" height="5" fill="#92400e" opacity="0.7" />
        <path className="leaveHero-steam" d="M98 152 q-4 -6 0 -12" stroke="#94a3b8" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path className="leaveHero-steam leaveHero-steam-b" d="M104 152 q4 -6 0 -12" stroke="#94a3b8" strokeWidth="2" fill="none" strokeLinecap="round" />
        <text x="76" y="148" textAnchor="middle" fontSize="8" fontWeight="800" fill="#64748b">Cup #5</text>
        <text className="leaveHero-z leaveHero-z-a" x="258" y="82" fontSize="15" fontWeight="800" fill="#6366f1">z</text>
        <text className="leaveHero-z leaveHero-z-b" x="270" y="70" fontSize="19" fontWeight="800" fill="#6366f1">Z</text>
        <text className="leaveHero-z leaveHero-z-c" x="284" y="56" fontSize="23" fontWeight="800" fill="#6366f1">Z</text>
      </g>
    )
  }

  if (mood === 'excited') {
    return (
      <g>
        <Desk />
        <rect x="298" y="172" width="80" height="6" rx="3" fill="#94a3b8" />
        <g>
          <animateTransform
            attributeName="transform"
            type="rotate"
            values="0 298 172;0 298 172;86 298 172;86 298 172;0 298 172"
            keyTimes="0;0.35;0.55;0.85;1"
            dur="5s"
            repeatCount="indefinite"
          />
          <rect x="298" y="124" width="80" height="48" rx="4" fill="#334155" />
          <rect x="303" y="129" width="70" height="38" fill="#38bdf8" opacity="0.4" />
          <text x="338" y="153" textAnchor="middle" fontSize="13" fontWeight="900" fill="#fff">OOO</text>
        </g>
        <g className="leaveHero-hop">
          <rect x="40" y="146" width="52" height="32" rx="5" fill="#f97316" />
          <path d="M56 146 v-8 h20 v8" stroke="#7c2d12" strokeWidth="3" fill="none" />
          <line x1="52" y1="146" x2="52" y2="178" stroke="#c2410c" strokeWidth="3" />
          <line x1="80" y1="146" x2="80" y2="178" stroke="#c2410c" strokeWidth="3" />
          <circle cx="66" cy="162" r="5" fill="#fde047" />
          <circle cx="86" cy="168" r="3.5" fill="#34d399" />
        </g>
        {[0, 1.3, 2.6].map((delay) => (
          <g key={delay} transform="translate(308 128)">
            <path className="leaveHero-plane" d="M0 0 L18 -6 L7 2 L5 9 Z" fill="#fff" stroke="#94a3b8" strokeWidth="1" style={{ animationDelay: `${delay}s` }} />
          </g>
        ))}
        {CONFETTI.map((piece, index) => (
          <rect
            key={index}
            className="leaveHero-confetti"
            x={piece.x}
            y="-12"
            width={piece.size}
            height={piece.size * 1.6}
            fill={piece.color}
            style={{ animationDelay: `${piece.delay}s` }}
          />
        ))}
      </g>
    )
  }

  if (mood === 'sweating') {
    return (
      <g>
        <Desk />
        <Monitor>
          <text x="303" y="123" fontSize="7.5" fontWeight="800" fill="#94a3b8">Approved?</text>
          <circle cx="342" cy="138" r="13" fill="none" stroke="#334155" strokeWidth="4" />
          <circle cx="342" cy="138" r="13" fill="none" stroke="#38bdf8" strokeWidth="4" strokeDasharray="22 60" strokeLinecap="round">
            <animateTransform attributeName="transform" type="rotate" from="0 342 138" to="360 342 138" dur="0.9s" repeatCount="indefinite" />
          </circle>
          <text x="342" y="159" textAnchor="middle" fontSize="8.5" fontWeight="800" fill="#e2e8f0">F5 x {refreshes}</text>
        </Monitor>
        <g>
          <rect x="44" y="170" width="24" height="8" rx="2" fill="#64748b" />
          <rect x="54" y="148" width="4" height="22" fill="#64748b" />
          <circle cx="56" cy="138" r="15" fill="#e2e8f0" stroke="#94a3b8" strokeWidth="2" />
          <g>
            <animateTransform attributeName="transform" type="rotate" from="0 56 138" to="360 56 138" dur="0.35s" repeatCount="indefinite" />
            <path d="M56 138 L56 125 M56 138 L67 144 M56 138 L45 144" stroke="#475569" strokeWidth="3" strokeLinecap="round" />
          </g>
        </g>
        <g className="leaveHero-flutter">
          <rect x="82" y="150" width="16" height="20" fill="#fff" stroke="#cbd5e1" />
          <rect x="94" y="156" width="16" height="20" fill="#f1f5f9" stroke="#cbd5e1" />
        </g>
        <g className="leaveHero-buzz">
          <rect x="116" y="168" width="28" height="10" rx="3" fill="#1f2937" />
          <rect x="118" y="170" width="24" height="6" rx="1.5" fill="#38bdf8" opacity="0.7" />
        </g>
      </g>
    )
  }

  return (
    <g>
      <g transform="rotate(-14 331 202)">
        <rect x="304" y="184" width="54" height="36" rx="3" fill="#334155" />
        <rect x="309" y="189" width="44" height="26" fill="#38bdf8" opacity="0.4" />
        <text x="331" y="206" textAnchor="middle" fontSize="10" fontWeight="900" fill="#fff">zzz</text>
      </g>
      <line x1="372" y1="212" x2="372" y2="168" stroke="#92400e" strokeWidth="3" strokeLinecap="round" />
      <g className="leaveHero-flag">
        <path d="M372 168 h28 l-6 8 l6 8 h-28 Z" fill="#ef4444" />
        <text x="385" y="179" textAnchor="middle" fontSize="7" fontWeight="900" fill="#fff">OOO</text>
      </g>
      <path d="M0 208 Q40 200 90 208 T200 208 T320 208 T420 208 V240 H0 Z" fill="#fcd34d" />
      <g transform="translate(40 226)">
        <g className="leaveHero-crab">
          <ellipse cx="0" cy="0" rx="12" ry="8" fill="#f87171" />
          <circle cx="-5" cy="-9" r="2.8" fill="#fff" />
          <circle cx="5" cy="-9" r="2.8" fill="#fff" />
          <circle cx="-5" cy="-9" r="1.2" fill="#1f2937" />
          <circle cx="5" cy="-9" r="1.2" fill="#1f2937" />
          <circle className="leaveHero-claw" cx="-17" cy="-4" r="5" fill="#ef4444" />
          <circle className="leaveHero-claw leaveHero-claw-b" cx="17" cy="-4" r="5" fill="#ef4444" />
          <path d="M-9 6 l-5 5 M-4 8 l-3 6 M4 8 l3 6 M9 6 l5 5" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" />
        </g>
      </g>
      <g transform="rotate(-14 250 222)">
        <g className="leaveHero-buzz">
          <rect x="238" y="214" width="22" height="14" rx="3" fill="#1f2937" />
          <circle cx="259" cy="214" r="6" fill="#ef4444" />
          <text x="259" y="217" textAnchor="middle" fontSize="7" fontWeight="900" fill="#fff">47</text>
        </g>
      </g>
      <text x="250" y="237" textAnchor="middle" fontSize="8" fontWeight="800" fill="#92400e">ignored</text>
    </g>
  )
}

function LeaveHero({ mood }) {
  const [jokeIndex, setJokeIndex] = useState(0)
  const [thoughtIndex, setThoughtIndex] = useState(0)
  const [poke, setPoke] = useState(null)
  const [refreshes, setRefreshes] = useState(14)
  const copy = HERO_COPY[mood] || HERO_COPY.tired
  const joke = copy.jokes[jokeIndex % copy.jokes.length]
  const bubbleText = poke ? poke.text : copy.thoughts[thoughtIndex % copy.thoughts.length]

  useEffect(() => {
    setJokeIndex(0)
    setThoughtIndex(0)
    setPoke(null)
  }, [mood])

  useEffect(() => {
    const id = window.setInterval(() => setThoughtIndex((current) => current + 1), 5200)
    return () => window.clearInterval(id)
  }, [mood])

  useEffect(() => {
    if (mood !== 'sweating') return undefined
    const id = window.setInterval(() => setRefreshes((current) => current + 1), 1400)
    return () => window.clearInterval(id)
  }, [mood])

  useEffect(() => {
    if (!poke) return undefined
    const id = window.setTimeout(() => setPoke(null), 2600)
    return () => window.clearTimeout(id)
  }, [poke])

  function pokeWorker() {
    const text = copy.pokes[Math.floor(Math.random() * copy.pokes.length)]
    setPoke({ text, key: Date.now() })
  }

  return (
    <section className={`leaveHero leaveHero-${mood}`} aria-label="Leave mood">
      <div className="leaveHero-copy">
        <span className="leaveHero-chip">{copy.emoji} Mood: {mood}</span>
        <h2>{copy.title}</h2>
        <p>{copy.text}</p>
        <div className="leaveHero-joke">
          <span>“{joke}”</span>
          <button type="button" onClick={() => setJokeIndex((current) => current + 1)}>Another one</button>
        </div>
        <div className="leaveHero-feed" aria-hidden="true">
          {copy.feed.map(([icon, text], index) => (
            <span key={`${mood}-${index}`} className="leaveHero-feed-item" style={{ animationDelay: `${index * 3}s` }}>
              <b>{icon}</b>
              {text}
            </span>
          ))}
        </div>
      </div>

      <button type="button" className="leaveHero-stage" onClick={pokeWorker} aria-label="Poke the worker for a reaction">
        <span key={poke ? poke.key : `thought-${thoughtIndex}`} className="leaveHero-bubble">{bubbleText}</span>
        <svg viewBox="0 0 420 240" className="leaveHero-svg" aria-hidden="true">
          <SceneBack mood={mood} />
          <g transform="translate(90 22)">
            <g key={poke ? poke.key : 'idle'} className={poke ? 'leaveHero-poked' : undefined}>
              <LeaveWorker mood={mood} />
            </g>
          </g>
          <SceneFront mood={mood} refreshes={refreshes} />
        </svg>
        <span className="leaveHero-hint">Poke the human</span>
      </button>
    </section>
  )
}

function LeaveManagement({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role)
  const isAdmin = role === 'ADMIN'
  const isAgent = role === 'AGENT'
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
  const [managerName, setManagerName] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [copyState, setCopyState] = useState('idle')
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [loading, setLoading] = useState(true)
  const [summarySaving, setSummarySaving] = useState(false)
  const options = useMemo(() => monthOptions(), [])
  const leaveEmailTemplate = useMemo(() => buildLeaveEmailTemplate(form, policy, managerName), [form, policy, managerName])
  const heroMood = useMemo(() => {
    if (form.start_date) return 'excited'
    if (requests.some((item) => item.status === 'PENDING')) return 'sweating'
    if (requests.some((item) => item.status === 'APPROVED')) return 'beach'
    return 'tired'
  }, [form.start_date, requests])

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

  function updateManagerName(value) {
    setManagerName(value)
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

        {isAgent ? <LeaveHero mood={heroMood} /> : null}

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
                Reason (optional)
                <textarea value={form.reason} onChange={(event) => updateForm('reason', event.target.value)} />
              </label>
              <label className="leaveModule-span">
                Manager&apos;s Name
                <input
                  type="text"
                  value={managerName}
                  onChange={(event) => updateManagerName(event.target.value)}
                  placeholder="Enter manager name for copied email"
                />
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
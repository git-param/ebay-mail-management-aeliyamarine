import { useEffect, useMemo, useRef, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import {
  createPmsConfig,
  deletePmsConfig,
  fetchPmsConfig,
  fetchPmsEmployeeOfMonth,
  fetchPmsHistory,
  fetchPmsMonthlyRecord,
  fetchPmsMonthlyTable,
  refreshPmsAutoValues,
  resolvePmsEmployeeOfMonth,
  savePmsMonthly,
  updatePmsConfig,
} from '../../services/pmsApi'
import { normalizeRole } from '../../utils/roles'

import './pms.css'

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function monthLabel(year, month) {
  return `${MONTH_NAMES[month - 1]} ${year}`
}

// Last 24 months, most recent first.
// Admin/Ops Manager can navigate previous months without limiting editing.
function buildMonthOptions() {
  const options = []
  const now = new Date()

  for (let i = 0; i < 24; i += 1) {
    const d = new Date(
      now.getFullYear(),
      now.getMonth() - i,
      1,
    )

    options.push({
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      label: monthLabel(
        d.getFullYear(),
        d.getMonth() + 1,
      ),
    })
  }

  return options
}

function fmt(value, decimals = 1) {
  if (
    value === null
    || value === undefined
    || Number.isNaN(Number(value))
  ) {
    return '-'
  }

  return Number(value)
    .toFixed(decimals)
    .replace(/\.0$/, '')
}

function clampNumber(value, max) {
  const n = Number(value)

  if (Number.isNaN(n)) {
    return 0
  }

  return Math.max(
    0,
    Math.min(n, max),
  )
}

function statusBadgeClass(status) {
  if (status === 'COMPLETED') {
    return 'pmsModule-badge pmsModule-badge-completed'
  }

  if (status === 'DRAFT') {
    return 'pmsModule-badge pmsModule-badge-draft'
  }

  return 'pmsModule-badge pmsModule-badge-pending'
}

function metricTooltip(metric) {
  const meta = metric.calc_meta

  if (!meta) {
    return null
  }

  if (
    metric.source_snapshot === 'QUALITY_AUTO'
  ) {
    return (
      `${meta.formula || ''} `
      + `Based on ${meta.working_days ?? 0} working day(s) - `
      + `SLA avg ${fmt(meta.sla_avg_pct)}% - `
      + `${meta.major_error_days ?? 0} Major, `
      + `${meta.minor_error_days ?? 0} Minor error day(s).`
    )
  }

  if (
    metric.source_snapshot
    === 'PRODUCTIVITY_AUTO'
  ) {
    return (
      `${meta.formula || ''} `
      + `Based on ${meta.working_days ?? 0} working day(s) - `
      + `task completion avg ${fmt(meta.task_completion_avg_pct)}%.`
    )
  }

  return meta.formula || null
}

function initials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    || 'P'
}

function scorePercent(value, max) {
  const score = Number(value)
  const maximum = Number(max)

  if (
    Number.isNaN(score)
    || Number.isNaN(maximum)
    || maximum <= 0
  ) {
    return 0
  }

  return Math.max(
    0,
    Math.min(
      100,
      (score / maximum) * 100,
    ),
  )
}

/**
 * Copy text with a fallback for browsers/environments where the modern
 * Clipboard API is unavailable or blocked.
 */
async function copyTextToClipboard(text) {
  if (
    navigator.clipboard
    && typeof navigator.clipboard.writeText === 'function'
  ) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Continue to the legacy fallback below.
    }
  }

  const textarea = document.createElement('textarea')

  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  textarea.style.opacity = '0'

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

export function PMS({
  currentUser,
  onLogout,
}) {
  const role = normalizeRole(
    currentUser?.role,
  )

  const isAdmin = role === 'ADMIN'
  const isOpsManager = role === 'OPS_MANAGER'
  const isAgent = role === 'AGENT'

  const canViewAll = (
    isAdmin
    || isOpsManager
  )

  const monthOptions = useMemo(
    () => buildMonthOptions(),
    [],
  )

  const [selectedYear, setSelectedYear] = useState(
    monthOptions[0].year,
  )

  const [selectedMonth, setSelectedMonth] = useState(
    monthOptions[0].month,
  )

  const [activeTab, setActiveTab] = useState('monthly')
  const [search, setSearch] = useState('')

  const [tableData, setTableData] = useState(null)
  const [tableLoading, setTableLoading] = useState(false)
  const [tableError, setTableError] = useState(null)

  // Employee of the Month has its own loading/error state.
  // Previously every API error was silently converted to eomData=null,
  // making a backend failure look exactly like "no completed PMS records".
  const [eomData, setEomData] = useState(null)
  const [eomLoading, setEomLoading] = useState(false)
  const [eomError, setEomError] = useState(null)

  const [copyState, setCopyState] = useState('idle')

  const [agentRecord, setAgentRecord] = useState(null)
  const [agentLoading, setAgentLoading] = useState(false)

  const [editorUser, setEditorUser] = useState(null)
  const [editorRecord, setEditorRecord] = useState(null)
  const [editorMetrics, setEditorMetrics] = useState([])
  const [editorRemarks, setEditorRemarks] = useState('')
  const [editorLoading, setEditorLoading] = useState(false)
  const [editorSaving, setEditorSaving] = useState(false)
  const [editorError, setEditorError] = useState(null)
  const [editorRefreshing, setEditorRefreshing] = useState(false)

  const [configItems, setConfigItems] = useState([])
  const [configTotalWeight, setConfigTotalWeight] = useState(0)
  const [configLoading, setConfigLoading] = useState(false)
  const [configError, setConfigError] = useState(null)
  const [newMetricOpen, setNewMetricOpen] = useState(false)

  const [historyFilters, setHistoryFilters] = useState({
    year: '',
    month: '',
    search: '',
    status: '',
  })

  const [historyData, setHistoryData] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyDetail, setHistoryDetail] = useState(null)

  const copyResetRef = useRef(null)

  const leaderboardRows = useMemo(
    () => {
      const items = tableData?.items || []

      return [...items].sort((a, b) => {
        const scoreA = Number(a.final_score) || 0
        const scoreB = Number(b.final_score) || 0

        return scoreB - scoreA
      })
    },
    [tableData],
  )

  const displayedTopPerformer = useMemo(
    () => {
      const hasSelectedMonthWinner = (
        eomData?.winner
        && eomData.year === selectedYear
        && eomData.month === selectedMonth
      )

      if (hasSelectedMonthWinner) {
        return {
          name: eomData.winner.user_name,
          score: eomData.winner.final_score,
        }
      }

      return {
        name: tableData?.top_performer_name || '',
        score: tableData?.top_performer_score ?? null,
      }
    },
    [eomData, selectedMonth, selectedYear, tableData],
  )

  const dashboardInsights = useMemo(
    () => {
      if (!tableData) {
        return []
      }

      const items = tableData.items || []
      const completed = Number(tableData.completed_count) || 0
      const total = items.length
      const aboveNinety = items.filter(
        (item) => (
          scorePercent(
            item.final_score,
            item.maximum_score,
          ) >= 90
        ),
      ).length

      return [
        `${completed} of ${total} evaluations are completed.`,
        `${aboveNinety} employee${aboveNinety === 1 ? '' : 's'} scored at or above 90%.`,
        displayedTopPerformer.name
          ? `${displayedTopPerformer.name} is the selected top performer.`
          : 'No top performer has been published yet.',
      ]
    },
    [displayedTopPerformer.name, tableData],
  )

  useEffect(
    () => () => {
      if (copyResetRef.current) {
        window.clearTimeout(copyResetRef.current)
      }
    },
    [],
  )

  // ------------------------------------------------------------------
  // Loaders
  // ------------------------------------------------------------------

  async function loadMonthlyTable() {
    setTableLoading(true)
    setTableError(null)

    try {
      const data = await fetchPmsMonthlyTable({
        year: selectedYear,
        month: selectedMonth,
        search: search || undefined,
      })

      setTableData(data)
    } catch (err) {
      setTableError(
        err?.message
        || 'Failed to load PMS for this month.',
      )
    } finally {
      setTableLoading(false)
    }
  }

  async function loadEmployeeOfMonth() {
    setEomLoading(true)
    setEomError(null)

    try {
      const data = await fetchPmsEmployeeOfMonth({
        year: selectedYear,
        month: selectedMonth,
      })

      setEomData(data)
    } catch (err) {
      setEomData(null)

      // Do not hide a backend/API error behind the "no records" message.
      setEomError(
        err?.message
        || 'Failed to load Employee of the Month.',
      )
    } finally {
      setEomLoading(false)
    }
  }

  async function loadAgentRecord() {
    if (
      !isAgent
      || !currentUser?.id
    ) {
      return
    }

    setAgentLoading(true)

    try {
      const data = await fetchPmsMonthlyRecord(
        currentUser.id,
        {
          year: selectedYear,
          month: selectedMonth,
        },
      )

      setAgentRecord(data)
    } catch {
      setAgentRecord(null)
    } finally {
      setAgentLoading(false)
    }
  }

  async function loadConfig() {
    setConfigLoading(true)
    setConfigError(null)

    try {
      const data = await fetchPmsConfig()

      setConfigItems(
        data.items || [],
      )

      setConfigTotalWeight(
        data.total_active_weight || 0,
      )
    } catch (err) {
      setConfigError(
        err?.message
        || 'Failed to load PMS configuration.',
      )
    } finally {
      setConfigLoading(false)
    }
  }

  async function loadHistory() {
    setHistoryLoading(true)

    try {
      const data = await fetchPmsHistory({
        year: historyFilters.year || undefined,
        month: historyFilters.month || undefined,
        search: historyFilters.search || undefined,
        status: historyFilters.status || undefined,
      })

      setHistoryData(data)
    } catch {
      setHistoryData(null)
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (canViewAll) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadMonthlyTable()
    }

    loadEmployeeOfMonth()

    if (isAgent) {
      loadAgentRecord()
    }

    // A copy-success message from a previous month should never remain
    // visible after the Admin selects a different month.
    setCopyState('idle')

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    selectedYear,
    selectedMonth,
  ])

  useEffect(() => {
    if (!canViewAll) {
      return undefined
    }

    const timeout = window.setTimeout(
      loadMonthlyTable,
      300,
    )

    return () => {
      window.clearTimeout(timeout)
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  useEffect(() => {
    if (
      activeTab === 'config'
      && isAdmin
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadConfig()
    }

    if (
      activeTab === 'history'
    ) {
      loadHistory()
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  useEffect(() => {
    if (
      activeTab === 'history'
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadHistory()
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyFilters])

  // ------------------------------------------------------------------
  // Editor drawer
  // ------------------------------------------------------------------

  async function openEditor(user) {
    setEditorUser(user)
    setEditorError(null)
    setEditorLoading(true)

    try {
      const record = await fetchPmsMonthlyRecord(
        user.user_id,
        {
          year: selectedYear,
          month: selectedMonth,
        },
      )

      setEditorRecord(record)

      setEditorMetrics(
        record.metrics.map(
          (metric) => ({
            ...metric,
          }),
        ),
      )

      setEditorRemarks(
        record.remarks || '',
      )
    } catch (err) {
      setEditorError(
        err?.message
        || "Failed to load this employee's PMS.",
      )
    } finally {
      setEditorLoading(false)
    }
  }

  function closeEditor() {
    setEditorUser(null)
    setEditorRecord(null)
    setEditorMetrics([])
    setEditorError(null)
  }

  function updateMetricValue(
    key,
    value,
  ) {
    setEditorMetrics(
      (items) => items.map(
        (item) => {
          if (
            item.metric_key !== key
          ) {
            return item
          }

          const clamped = clampNumber(
            value,
            item.weight_snapshot,
          )

          return {
            ...item,
            final_value: clamped,
          }
        },
      ),
    )
  }

  const editorFinalScore = useMemo(
    () => editorMetrics.reduce(
      (sum, item) => (
        sum
        + (
          Number(item.final_value)
          || 0
        )
      ),
      0,
    ),
    [editorMetrics],
  )

  const editorMaxScore = useMemo(
    () => editorMetrics.reduce(
      (sum, item) => (
        sum
        + (
          Number(item.weight_snapshot)
          || 0
        )
      ),
      0,
    ),
    [editorMetrics],
  )

  async function refreshEditorAutoValues() {
    if (!editorUser) {
      return
    }

    setEditorRefreshing(true)

    try {
      const record = await refreshPmsAutoValues({
        user_id: editorUser.user_id,
        year: selectedYear,
        month: selectedMonth,
      })

      setEditorRecord(record)

      setEditorMetrics(
        record.metrics.map(
          (metric) => ({
            ...metric,
          }),
        ),
      )
    } catch (err) {
      setEditorError(
        err?.message
        || 'Failed to refresh auto-calculated values.',
      )
    } finally {
      setEditorRefreshing(false)
    }
  }

  async function saveEditor(status) {
    if (!editorUser) {
      return
    }

    setEditorSaving(true)
    setEditorError(null)

    try {
      const payload = {
        user_id: editorUser.user_id,
        year: selectedYear,
        month: selectedMonth,
        remarks: editorRemarks || null,
        status,
        metrics: editorMetrics.map(
          (metric) => ({
            metric_key: metric.metric_key,
            final_value:
              Number(metric.final_value) || 0,
          }),
        ),
      }

      await savePmsMonthly(payload)

      closeEditor()

      await loadMonthlyTable()
      await loadEmployeeOfMonth()
    } catch (err) {
      setEditorError(
        err?.message
        || 'Failed to save PMS.',
      )
    } finally {
      setEditorSaving(false)
    }
  }

  // ------------------------------------------------------------------
  // Config
  // ------------------------------------------------------------------

  async function deleteConfigItem(item) {
    const confirmed = window.confirm(
      `Delete "${item.name}" from PMS Configuration?`,
    )

    if (!confirmed) {
      return
    }

    try {
      await deletePmsConfig(
        item.id,
      )

      setConfigItems(
        (items) => items.filter(
          (existing) => existing.id !== item.id,
        ),
      )

      loadConfig()
    } catch (err) {
      setConfigError(
        err?.message
        || 'Failed to delete metric.',
      )
    }
  }

  async function saveConfigWeight(
    item,
    weight,
  ) {
    try {
      const updated = await updatePmsConfig(
        item.id,
        {
          weight: Number(weight),
        },
      )

      setConfigItems(
        (items) => items.map(
          (existing) => (
            existing.id === item.id
              ? updated
              : existing
          ),
        ),
      )

      loadConfig()
    } catch (err) {
      setConfigError(
        err?.message
        || 'Failed to update weight.',
      )
    }
  }

  async function submitNewMetric(event) {
    event.preventDefault()

    const form = event.target

    const payload = {
      key: form.key.value.trim(),
      name: form.name.value.trim(),
      weight:
        Number(form.weight.value) || 0,
      source: 'MANUAL',
      is_auto_calculated: false,
      is_manually_editable: true,
      is_active: true,
      display_order:
        configItems.length + 1,
      description:
        form.description.value.trim()
        || null,
    }

    try {
      await createPmsConfig(payload)

      setNewMetricOpen(false)

      form.reset()

      loadConfig()
    } catch (err) {
      setConfigError(
        err?.message
        || 'Failed to create metric.',
      )
    }
  }

  // ------------------------------------------------------------------
  // Employee of the Month
  // ------------------------------------------------------------------

  async function copyEmployeeOfMonth() {
    if (!eomData?.winner) {
      return
    }

    const winner = eomData.winner

    const label = monthLabel(
      eomData.year,
      eomData.month,
    )

    const lines = [
      `🏆 Employee of the Month - ${label}`,
      '',
      `Congratulations to ${winner.user_name} for achieving the highest PMS score for ${label}.`,
      '',
      `Final Score: ${fmt(winner.final_score)}/${fmt(winner.maximum_score)}`,
      '',
      'Performance Breakdown:',
      ...winner.metrics.map(
        (metric) => (
          `- ${metric.metric_name_snapshot}: ${fmt(metric.final_value)}/${fmt(metric.weight_snapshot)}`
        ),
      ),
      '',
      'Excellent performance and contribution throughout the month.',
    ]

    const text = lines.join('\n')

    try {
      await copyTextToClipboard(text)

      setCopyState('copied')
    } catch {
      setCopyState('failed')
    } finally {
      if (copyResetRef.current) {
        window.clearTimeout(copyResetRef.current)
      }

      copyResetRef.current = window.setTimeout(
        () => {
          setCopyState('idle')
          copyResetRef.current = null
        },
        1600,
      )
    }
  }

  async function resolveTie(userId) {
    try {
      const data = await resolvePmsEmployeeOfMonth({
        year: selectedYear,
        month: selectedMonth,
        selected_user_id: userId,
      })

      setEomData(data)
      setEomError(null)
      setCopyState('idle')
    } catch (err) {
      setEomError(
        err?.message
        || 'Failed to select Employee of the Month.',
      )
    }
  }

  // ------------------------------------------------------------------
  // Render helpers
  // ------------------------------------------------------------------

  function renderMonthSelector() {
    return (
      <select
        className="pmsModule-month-select"
        value={`${selectedYear}-${selectedMonth}`}
        onChange={(event) => {
          const [year, month] = (
            event.target.value
              .split('-')
              .map(Number)
          )

          setSelectedYear(year)
          setSelectedMonth(month)
        }}
      >
        {monthOptions.map((option) => (
          <option
            key={`${option.year}-${option.month}`}
            value={`${option.year}-${option.month}`}
          >
            {option.label}
          </option>
        ))}
      </select>
    )
  }

  function renderSummaryCards() {
    if (!tableData) {
      return null
    }

    const employeeCount = tableData.items.length
    const completedPercent = employeeCount
      ? (tableData.completed_count / employeeCount) * 100
      : 0
    const pendingPercent = employeeCount
      ? (tableData.pending_count / employeeCount) * 100
      : 0
    const averagePercent = scorePercent(
      tableData.average_score,
      tableData.total_active_weight || 100,
    )

    return (
      <section className="pmsModule-overview-panel">
        <div className="pmsModule-overview-lead">
          <span>Monthly Control</span>
          <strong>{fmt(completedPercent)}% complete</strong>
          <small>{monthLabel(selectedYear, selectedMonth)}</small>
        </div>

        <div className="pmsModule-summary-grid">
          <div className="pmsModule-summary-card">
            <span>Employees</span>
            <strong>{employeeCount}</strong>
            <div className="pmsModule-mini-meter">
              <i style={{ width: '100%' }} />
            </div>
          </div>

          <div className="pmsModule-summary-card">
            <span>PMS Completed</span>
            <strong>{tableData.completed_count}</strong>
            <div className="pmsModule-mini-meter">
              <i style={{ width: `${completedPercent}%` }} />
            </div>
          </div>

          <div className="pmsModule-summary-card">
            <span>Pending</span>
            <strong>{tableData.pending_count}</strong>
            <div className="pmsModule-mini-meter pmsModule-mini-meter-warm">
              <i style={{ width: `${pendingPercent}%` }} />
            </div>
          </div>

          <div className="pmsModule-summary-card">
            <span>Average Score</span>
            <strong>
              {tableData.average_score !== null
                ? fmt(tableData.average_score)
                : '-'}
            </strong>
            <div className="pmsModule-mini-meter">
              <i style={{ width: `${averagePercent}%` }} />
            </div>
          </div>

          <div className="pmsModule-summary-card pmsModule-summary-card-highlight">
            <span>Top Performer</span>
            <strong>{displayedTopPerformer.name || '-'}</strong>
            {displayedTopPerformer.score !== null ? (
              <small>{fmt(displayedTopPerformer.score)}</small>
            ) : null}
          </div>
        </div>

        {tableData.total_active_weight !== 100 ? (
          <div className="pmsModule-summary-card pmsModule-summary-card-warning">
            <span>Configured Total Weight</span>
            <strong>{fmt(tableData.total_active_weight)}</strong>
            <small>
              Active weights don't total 100 - check PMS Configuration.
            </small>
          </div>
        ) : null}

        <div className="pmsModule-insights">
          {dashboardInsights.map((insight) => (
            <span key={insight}>{insight}</span>
          ))}
        </div>
      </section>
    )
  }
  function renderEmployeeOfMonth() {
    if (eomLoading) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-empty pmsModule-skeleton-panel">
          <div className="pmsModule-award-outline" />
          <div>
            <h3>Winner Spotlight</h3>
            <p>
              Loading Employee of the Month for{' '}
              {monthLabel(selectedYear, selectedMonth)}...
            </p>
          </div>
        </section>
      )
    }

    if (eomError) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-empty">
          <div className="pmsModule-award-outline" />
          <div>
            <h3>Winner Spotlight</h3>
            <div className="form-message error">{eomError}</div>
            <button
              type="button"
              className="secondary-button"
              onClick={loadEmployeeOfMonth}
            >
              <Icon name="refresh" /> Retry
            </button>
          </div>
        </section>
      )
    }

    if (!eomData || (!eomData.winner && !eomData.is_tie)) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-empty">
          <div className="pmsModule-award-outline" />
          <div>
            <h3>Winner Spotlight</h3>
            <p>
              No completed PMS records yet for{' '}
              {monthLabel(selectedYear, selectedMonth)}.
            </p>
          </div>
        </section>
      )
    }

    if (eomData.is_tie && !eomData.winner) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-tie">
          <div className="pmsModule-eom-copy">
            <span className="pmsModule-eyebrow">Winner Decision</span>
            <h3>Joint Top Performers</h3>
            <p>
              {eomData.candidates.length}{' '}
              employees are tied for the highest score this month.
            </p>
          </div>

          <ul className="pmsModule-eom-tie-list">
            {eomData.candidates.map((candidate) => (
              <li key={candidate.user_id}>
                <span>{candidate.user_name}</span>
                <strong>{fmt(candidate.final_score)}</strong>

                {isAdmin ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => resolveTie(candidate.user_id)}
                  >
                    Select as winner
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )
    }

    const winner = eomData.winner
    const percent = scorePercent(
      winner.final_score,
      winner.maximum_score,
    )

    return (
      <section className="pmsModule-eom-card pmsModule-winner-spotlight">
        <div className="pmsModule-eom-copy">
          <span className="pmsModule-eyebrow">
            Employee of the Month{eomData.is_tie ? ' - tie resolved' : ''}
          </span>

          <div className="pmsModule-winner-identity">
            <div className="pmsModule-avatar">
              {initials(winner.user_name)}
            </div>

            <div>
              <h3>{winner.user_name}</h3>
              <p>Final PMS Score</p>
            </div>
          </div>

          <div className="pmsModule-eom-score">
            <strong>{fmt(winner.final_score)}</strong>
            <span>/ {fmt(winner.maximum_score)}</span>
          </div>

          <div
            className="pmsModule-score-track"
            aria-label={`Winner score ${fmt(percent)} percent`}
          >
            <i style={{ width: `${percent}%` }} />
          </div>

          <div className="pmsModule-eom-actions">
            <button
              type="button"
              className={`secondary-button ${copyState === 'copied' ? 'pmsModule-button-success' : ''}`}
              onClick={copyEmployeeOfMonth}
            >
              <Icon name={copyState === 'copied' ? 'activate' : 'copy'} />
              {copyState === 'copied' ? 'Copied' : 'Copy to Clipboard'}
            </button>

            {copyState === 'failed' ? (
              <span className="pmsModule-copy-feedback error">
                Couldn't copy to clipboard.
              </span>
            ) : null}
          </div>
        </div>

        <div className="pmsModule-award-stage" aria-hidden="true">
          <div className="pmsModule-trophy-object">
            <span className="pmsModule-trophy-cup" />
            <span className="pmsModule-trophy-stem" />
            <span className="pmsModule-trophy-base" />
          </div>
        </div>

        <div className="pmsModule-eom-breakdown">
          {winner.metrics.map((metric) => {
            const metricPercent = scorePercent(
              metric.final_value,
              metric.weight_snapshot,
            )

            return (
              <div key={metric.metric_key}>
                <span>{metric.metric_name_snapshot}</span>
                <strong>
                  {fmt(metric.final_value)} / {fmt(metric.weight_snapshot)}
                </strong>
                <div className="pmsModule-metric-bar">
                  <i style={{ width: `${metricPercent}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </section>
    )
  }
  function renderMonthlyTable() {
    if (tableLoading) {
      return (
        <div className="pmsModule-empty-state pmsModule-skeleton-panel">
          Loading PMS for {monthLabel(selectedYear, selectedMonth)}...
        </div>
      )
    }

    if (tableError) {
      return <div className="pmsModule-empty-state error">{tableError}</div>
    }

    if (!tableData || tableData.items.length === 0) {
      return (
        <div className="pmsModule-empty-state">
          No PMS-eligible employees found{search ? ' for that search.' : '.'}
        </div>
      )
    }

    return (
      <section className="pmsModule-leaderboard">
        <div className="pmsModule-section-heading">
          <div>
            <span className="pmsModule-eyebrow">Leaderboard</span>
            <h2>Employee Performance Ranking</h2>
          </div>
          <small>{leaderboardRows.length} employees</small>
        </div>

        <div className="table-scroll">
          <table className="users-table pmsModule-monthly-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Employee</th>
                <th>Final Score</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {leaderboardRows.map((row, index) => {
                const percent = scorePercent(
                  row.final_score,
                  row.maximum_score,
                )
                const rank = index + 1

                return (
                  <tr
                    key={row.user_id}
                    className={rank <= 3 ? `pmsModule-rank-${rank}` : ''}
                  >
                    <td>
                      <span className="pmsModule-rank-badge">
                        {rank}
                      </span>
                    </td>

                    <td>
                      <div className="pmsModule-employee-cell">
                        <span className="pmsModule-avatar pmsModule-avatar-small">
                          {initials(row.user_name)}
                        </span>
                        <span>
                          <strong>{row.user_name}</strong>
                          {row.user_email ? (
                            <small className="pmsModule-table-subtext">
                              {row.user_email}
                            </small>
                          ) : null}
                        </span>
                      </div>
                    </td>

                    <td>
                      <div className="pmsModule-table-score">
                        <strong>
                          {row.final_score !== null
                            ? `${fmt(row.final_score)} / ${fmt(row.maximum_score)}`
                            : '-'}
                        </strong>
                        <div className="pmsModule-score-track">
                          <i style={{ width: `${percent}%` }} />
                        </div>
                      </div>
                    </td>

                    <td>
                      <span className={statusBadgeClass(row.status || 'PENDING')}>
                        {row.status || 'Not started'}
                      </span>
                    </td>

                    <td>
                      {isAdmin ? (
                        <button
                          type="button"
                          className="secondary-button compact-action"
                          onClick={() => openEditor(row)}
                        >
                          {row.record_id ? 'Edit PMS' : 'Enter PMS'}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="secondary-button compact-action"
                          onClick={() => openEditor(row)}
                          disabled={!row.record_id}
                        >
                          View
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    )
  }
  function renderEditorDrawer() {
    if (!editorUser) {
      return null
    }

    return (
      <div
        className="drawer-backdrop"
        onClick={closeEditor}
      >
        <div
          className="modal-panel pmsModule-editor-drawer"
          onClick={(event) => (
            event.stopPropagation()
          )}
        >
          <div className="drawer-header">
            <div>
              <strong>
                {editorUser.user_name}
              </strong>

              <p>
                {monthLabel(
                  selectedYear,
                  selectedMonth,
                )}
              </p>
            </div>

            <button
              type="button"
              className="icon-button"
              onClick={closeEditor}
              aria-label="Close"
            >
              <Icon name="close" />
            </button>
          </div>

          {editorLoading ? (
            <div className="pmsModule-empty-state">
              Loading...
            </div>
          ) : (
            <>
              {editorError ? (
                <div className="form-message error">
                  {editorError}
                </div>
              ) : null}

              <div className="pmsModule-editor-metrics">
                {editorMetrics.map(
                  (metric) => {
                    const isAuto = (
                      metric.is_auto_calculated_snapshot
                    )

                    const tooltip = metricTooltip(
                      metric,
                    )

                    const overridden = (
                      isAuto
                      && Number(
                        metric.final_value,
                      )
                      !== Number(
                        metric.auto_value,
                      )
                    )

                    return (
                      <div
                        className="pmsModule-editor-metric-row"
                        key={metric.metric_key}
                      >
                        <div className="pmsModule-editor-metric-label">
                          <div className="pmsModule-editor-metric-title">
                            <strong>
                              {metric.metric_name_snapshot}
                            </strong>

                            {isAuto ? (
                              <span
                                className={`source-badge ${
                                  overridden
                                    ? 'source-manual'
                                    : 'source-auto'
                                }`}
                              >
                                {overridden
                                  ? 'OVERRIDDEN'
                                  : 'AUTO'}
                              </span>
                            ) : null}

                            {tooltip ? (
                              <span className="pmsModule-info-trigger">
                                i

                                <span className="pmsModule-tooltip">
                                  {tooltip}
                                </span>
                              </span>
                            ) : null}
                          </div>

                          {isAuto ? (
                            <small className="pmsModule-auto-value">
                              Auto calculated:{' '}
                              {metric.auto_value !== null
                                ? fmt(metric.auto_value)
                                : '-'}
                              {' / '}
                              {fmt(metric.weight_snapshot)}
                            </small>
                          ) : null}
                        </div>

                        <div className="pmsModule-editor-metric-score">
                          <input
                            type="number"
                            min={0}
                            max={metric.weight_snapshot}
                            step="0.1"
                            disabled={
                              !editorRecord
                                ? false
                                : false
                            }
                            value={metric.final_value}
                            onChange={(event) => (
                              updateMetricValue(
                                metric.metric_key,
                                event.target.value,
                              )
                            )}
                          />

                          <span className="pmsModule-score-max">
                            /{' '}
                            {fmt(
                              metric.weight_snapshot,
                            )}
                          </span>
                        </div>
                      </div>
                    )
                  },
                )}
              </div>

              <div className="pmsModule-editor-final-row">
                <span>
                  Final Score
                </span>

                <strong>
                  {fmt(editorFinalScore)}
                  {' / '}
                  {fmt(editorMaxScore)}
                </strong>
              </div>

              <div className="field">
                <label htmlFor="pms-remarks">
                  Remarks
                </label>

                <textarea
                  id="pms-remarks"
                  value={editorRemarks}
                  onChange={(event) => (
                    setEditorRemarks(
                      event.target.value,
                    )
                  )}
                  rows={3}
                />
              </div>

              {isAdmin ? (
                <div className="modal-actions pmsModule-editor-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={refreshEditorAutoValues}
                    disabled={editorRefreshing}
                  >
                    <Icon name="refresh" />
                    {' '}
                    {editorRefreshing
                      ? 'Refreshing...'
                      : 'Refresh Auto Values'}
                  </button>

                  <div className="pmsModule-editor-save-group">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => (
                        saveEditor('DRAFT')
                      )}
                      disabled={editorSaving}
                    >
                      Save as Draft
                    </button>

                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => (
                        saveEditor('COMPLETED')
                      )}
                      disabled={editorSaving}
                    >
                      {editorSaving
                        ? 'Saving...'
                        : 'Save PMS'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="modal-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={closeEditor}
                  >
                    Close
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    )
  }

  function renderConfigTab() {
    if (!isAdmin) {
      return (
        <div className="pmsModule-empty-state">
          Only Admins can manage PMS configuration.
        </div>
      )
    }

    return (
      <div className="pmsModule-config-card">
        {configError ? (
          <div className="form-message error">
            {configError}
          </div>
        ) : null}

        {configLoading ? (
          <div className="pmsModule-empty-state">
            Loading configuration...
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Source</th>
                    <th>Weight</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>
                  {configItems.map(
                    (item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>
                            {item.name}
                          </strong>

                          {item.description ? (
                            <small className="pmsModule-table-subtext">
                              {item.description}
                            </small>
                          ) : null}
                        </td>

                        <td>
                          {item.source === 'MANUAL'
                            ? 'Manual'
                            : item.source === 'PRODUCTIVITY_AUTO'
                              ? 'Productivity (Daily Data)'
                              : item.source === 'QUALITY_AUTO'
                                ? 'Quality (Daily Data)'
                                : 'Custom'}
                        </td>

                        <td>
                          <input
                            type="number"
                            min={0}
                            className="pmsModule-config-weight-input"
                            defaultValue={item.weight}
                            onBlur={(event) => {
                              if (
                                Number(event.target.value)
                                !== item.weight
                              ) {
                                saveConfigWeight(
                                  item,
                                  event.target.value,
                                )
                              }
                            }}
                          />
                        </td>

                        <td>
                          <button
                            type="button"
                            className="secondary-button compact-action pmsModule-delete-action"
                            onClick={() => deleteConfigItem(item)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>

                <tfoot>
                  <tr>
                    <td colSpan={2}>
                      <strong>
                        Total Weight (active)
                      </strong>
                    </td>

                    <td colSpan={2}>
                      <strong>
                        {fmt(configTotalWeight)}
                        {configTotalWeight !== 100
                          ? ' warning not 100'
                          : ''}
                      </strong>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <div className="pmsModule-config-add">
              {newMetricOpen ? (
                <form
                  className="pmsModule-new-metric-form"
                  onSubmit={submitNewMetric}
                >
                  <div className="form-row">
                    <div className="field">
                      <label htmlFor="metric-key">
                        Key
                      </label>

                      <input
                        id="metric-key"
                        name="key"
                        placeholder="e.g. teamwork"
                        required
                      />
                    </div>

                    <div className="field">
                      <label htmlFor="metric-name">
                        Name
                      </label>

                      <input
                        id="metric-name"
                        name="name"
                        placeholder="e.g. Teamwork"
                        required
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="field">
                      <label htmlFor="metric-weight">
                        Weight
                      </label>

                      <input
                        id="metric-weight"
                        name="weight"
                        type="number"
                        min="0"
                        step="0.5"
                        required
                      />
                    </div>

                    <div className="field">
                      <label htmlFor="metric-description">
                        Description
                      </label>

                      <input
                        id="metric-description"
                        name="description"
                        placeholder="Optional"
                      />
                    </div>
                  </div>

                  <div className="modal-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => (
                        setNewMetricOpen(false)
                      )}
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      className="primary-button"
                    >
                      Add Metric
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => (
                    setNewMetricOpen(true)
                  )}
                >
                  + Add Metric
                </button>
              )}
            </div>

            <p className="pmsModule-config-note">
              New auto-calculated metrics
              (Productivity/Quality-style)
              aren&apos;t available from this
              form yet - only Manual metrics
              can be added here. Deactivating
              a metric hides it from future
              months without touching any
              historical PMS record.
            </p>
          </>
        )}
      </div>
    )
  }

  function renderHistoryTab() {
    return (
      <div className="pms-history-card">
        <div className="dailyEntry-history-filters pmsModule-history-filters">
          <div className="field">
            <label htmlFor="history-year">
              Year
            </label>

            <input
              id="history-year"
              type="number"
              value={historyFilters.year}
              onChange={(event) => (
                setHistoryFilters(
                  (filters) => ({
                    ...filters,
                    year: event.target.value,
                  }),
                )
              )}
              placeholder="e.g. 2026"
            />
          </div>

          <div className="field">
            <label htmlFor="history-month">
              Month
            </label>

            <select
              id="history-month"
              value={historyFilters.month}
              onChange={(event) => (
                setHistoryFilters(
                  (filters) => ({
                    ...filters,
                    month: event.target.value,
                  }),
                )
              )}
            >
              <option value="">
                All
              </option>

              {MONTH_NAMES.map(
                (name, index) => (
                  <option
                    key={name}
                    value={index + 1}
                  >
                    {name}
                  </option>
                ),
              )}
            </select>
          </div>

          {canViewAll ? (
            <div className="field">
              <label htmlFor="history-search">
                Employee
              </label>

              <input
                id="history-search"
                value={historyFilters.search}
                onChange={(event) => (
                  setHistoryFilters(
                    (filters) => ({
                      ...filters,
                      search:
                        event.target.value,
                    }),
                  )
                )}
                placeholder="Search name..."
              />
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="history-status">
              Status
            </label>

            <select
              id="history-status"
              value={historyFilters.status}
              onChange={(event) => (
                setHistoryFilters(
                  (filters) => ({
                    ...filters,
                    status:
                      event.target.value,
                  }),
                )
              )}
            >
              <option value="">
                All
              </option>

              <option value="COMPLETED">
                Completed
              </option>

              <option value="DRAFT">
                Draft
              </option>
            </select>
          </div>
        </div>

        {historyLoading ? (
          <div className="pmsModule-empty-state">
            Loading history...
          </div>
        ) : (
          !historyData
          || historyData.items.length === 0
        ) ? (
          <div className="pmsModule-empty-state">
            No PMS history matches these filters.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Month</th>

                  {canViewAll ? (
                    <th>Employee</th>
                  ) : null}

                  <th>Final Score</th>
                  <th>Percentage</th>
                  <th>Status</th>
                  <th>Last Updated</th>
                </tr>
              </thead>

              <tbody>
                {historyData.items.map(
                  (item) => (
                    <tr
                      key={item.record_id}
                      onClick={() => (
                        setHistoryDetail(
                          item,
                        )
                      )}
                    >
                      <td>
                        {monthLabel(
                          item.year,
                          item.month,
                        )}
                      </td>

                      {canViewAll ? (
                        <td>
                          {item.user_name}
                        </td>
                      ) : null}

                      <td>
                        {fmt(
                          item.final_score,
                        )}
                        {' / '}
                        {fmt(
                          item.maximum_score,
                        )}
                      </td>

                      <td>
                        {fmt(
                          item.percentage,
                        )}
                        %
                      </td>

                      <td>
                        <span
                          className={statusBadgeClass(
                            item.status,
                          )}
                        >
                          {item.status}
                        </span>
                      </td>

                      <td>
                        {new Date(
                          item.updated_at,
                        ).toLocaleDateString()}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}

        {historyDetail ? (
          <div
            className="modal-backdrop"
            onClick={() => (
              setHistoryDetail(null)
            )}
          >
            <div
              className="modal-panel"
              onClick={(event) => (
                event.stopPropagation()
              )}
            >
              <div className="drawer-header">
                <div>
                  <strong>
                    {historyDetail.user_name}
                  </strong>

                  <p>
                    {monthLabel(
                      historyDetail.year,
                      historyDetail.month,
                    )}
                  </p>
                </div>

                <button
                  type="button"
                  className="icon-button"
                  onClick={() => (
                    setHistoryDetail(null)
                  )}
                  aria-label="Close"
                >
                  <Icon name="close" />
                </button>
              </div>

              <p>
                Final Score:{' '}

                <strong>
                  {fmt(
                    historyDetail.final_score,
                  )}
                  {' / '}
                  {fmt(
                    historyDetail.maximum_score,
                  )}
                </strong>

                {' ('}
                {fmt(
                  historyDetail.percentage,
                )}
                %)
              </p>

              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setHistoryDetail(null)

                  openEditor({
                    user_id:
                      historyDetail.user_id,
                    user_name:
                      historyDetail.user_name,
                  })

                  setSelectedYear(
                    historyDetail.year,
                  )

                  setSelectedMonth(
                    historyDetail.month,
                  )
                }}
              >
                View Full Breakdown
              </button>
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  function renderAgentOwnRecord() {
    if (agentLoading) {
      return (
        <div className="pmsModule-empty-state">
          Loading your PMS...
        </div>
      )
    }

    if (
      !agentRecord
      || !agentRecord.id
    ) {
      return (
        <div className="pmsModule-empty-state">
          Your PMS for{' '}
          {monthLabel(
            selectedYear,
            selectedMonth,
          )}{' '}
          has not been published yet.
        </div>
      )
    }

    return (
      <div className="pms-entry-card pmsModule-agent-record">
        <div className="pmsModule-editor-final-row">
          <span>
            Final Score
          </span>

          <strong>
            {fmt(
              agentRecord.final_score,
            )}
            {' / '}
            {fmt(
              agentRecord.maximum_score,
            )}
          </strong>
        </div>

        <div className="pmsModule-editor-metrics">
          {agentRecord.metrics.map(
            (metric) => (
              <div
                className="pmsModule-editor-metric-row"
                key={metric.metric_key}
              >
                <div className="pmsModule-editor-metric-label">
                  <strong>
                    {metric.metric_name_snapshot}
                  </strong>
                </div>

                <div className="pmsModule-editor-metric-score">
                  <span>
                    {fmt(
                      metric.final_value,
                    )}
                    {' / '}
                    {fmt(
                      metric.weight_snapshot,
                    )}
                  </span>
                </div>
              </div>
            ),
          )}
        </div>

        {agentRecord.remarks ? (
          <p className="pmsModule-remarks-readout">
            Remarks:{' '}
            {agentRecord.remarks}
          </p>
        ) : null}
      </div>
    )
  }

  // ------------------------------------------------------------------
  // Main render
  // ------------------------------------------------------------------

  return (
    <AppLayout
      activePage="PMS"
      currentUser={currentUser}
      onLogout={onLogout}
    >
      <div className="pmsModule-page">
        <div className="page-header pmsModule-header">
          <div className="pmsModule-header-content">
            <span className="pmsModule-eyebrow">
              Performance Intelligence Center
            </span>

            <h1>PMS</h1>

            <p>
              Monitor achievement, productivity and team performance.
            </p>

            <div className="pmsModule-header-stats">
              <span>
                {monthLabel(selectedYear, selectedMonth)}
              </span>
              <span>
                {canViewAll
                  ? `${leaderboardRows.length} employees`
                  : 'Personal view'}
              </span>
            </div>
          </div>

          <div className="pmsModule-header-art" aria-hidden="true">
            <span className="pmsModule-glass-plane" />
            <span className="pmsModule-orbit-ring" />
            <span className="pmsModule-performance-core" />
          </div>
          <div className="pmsModule-header-controls">
            {renderMonthSelector()}

            {canViewAll ? (
              <input
                className="pmsModule-search-input"
                placeholder="Search employee..."
                value={search}
                onChange={(event) => (
                  setSearch(
                    event.target.value,
                  )
                )}
              />
            ) : null}
          </div>
        </div>

        <nav className="pmsModule-tabs">
          <button
            type="button"
            className={
              activeTab === 'monthly'
                ? 'active'
                : ''
            }
            onClick={() => (
              setActiveTab('monthly')
            )}
          >
            Monthly
          </button>

          <button
            type="button"
            className={
              activeTab === 'history'
                ? 'active'
                : ''
            }
            onClick={() => (
              setActiveTab('history')
            )}
          >
            History
          </button>

          {isAdmin ? (
            <button
              type="button"
              className={
                activeTab === 'config'
                  ? 'active'
                  : ''
              }
              onClick={() => (
                setActiveTab('config')
              )}
            >
              PMS Configuration
            </button>
          ) : null}
        </nav>

        {activeTab === 'monthly' ? (
          <>
            {renderEmployeeOfMonth()}

            {canViewAll ? (
              <>
                {renderSummaryCards()}

                <div className="pms-history-card">
                  {renderMonthlyTable()}
                </div>
              </>
            ) : (
              renderAgentOwnRecord()
            )}
          </>
        ) : null}

        {activeTab === 'history'
          ? renderHistoryTab()
          : null}

        {activeTab === 'config'
          ? renderConfigTab()
          : null}

        {renderEditorDrawer()}
      </div>
    </AppLayout>
  )
}

export default PMS

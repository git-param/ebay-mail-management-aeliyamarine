import { useEffect, useMemo, useRef, useState } from "react";

import AppLayout, { Icon } from "../../layouts/app_layout";
import {
  createPmsConfig,
  deletePmsConfig,
  exportPmsMonthlyTable,
  fetchPmsAvailablePeriods,
  fetchPmsConfig,
  fetchPmsEmployeeOfMonth,
  fetchPmsEmployeeOfMonthStats,
  fetchPmsHistory,
  fetchPmsMonthlyRecord,
  fetchPmsMonthlyTable,
  refreshPmsAutoValues,
  resolvePmsEmployeeOfMonth,
  savePmsMonthly,
  updatePmsConfig,
} from "../../services/pmsApi";
import { normalizeRole } from "../../utils/roles";

import "./pms.css";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const TARGET_ACHIEVEMENT_KEY = "target_achievement";
const TARGET_ACHIEVEMENT_STORAGE_KEY = "pms.targetAchievementByMonth";

function monthLabel(year, month) {
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

// Last 24 months, most recent first.
// Admin/Ops Manager can navigate previous months without limiting editing.
function buildMonthOptions() {
  const options = [];
  const now = new Date();

  for (let i = 0; i < 24; i += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);

    options.push({
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      label: monthLabel(d.getFullYear(), d.getMonth() + 1),
    });
  }

  return options;
}

function fmt(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }

  return Number(value).toFixed(decimals).replace(/\.0$/, "");
}

function roundScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return null;
  }

  const numeric = Number(value);
  const base = Math.floor(numeric);
  return base + (numeric - base >= 0.5 ? 1 : 0);
}

function fmtScore(value) {
  const rounded = roundScore(value);
  return rounded === null ? "-" : String(rounded);
}

function clampNumber(value, max) {
  const n = Number(value);

  if (Number.isNaN(n)) {
    return 0;
  }

  return Math.max(0, Math.min(n, max));
}

function statusBadgeClass(status) {
  if (status === "COMPLETED") {
    return "pmsModule-badge pmsModule-badge-completed";
  }

  if (status === "DRAFT") {
    return "pmsModule-badge pmsModule-badge-draft";
  }

  return "pmsModule-badge pmsModule-badge-pending";
}

function metricTooltip(metric) {
  const meta = metric.calc_meta;

  if (!meta) {
    return null;
  }

  if (metric.source_snapshot === "QUALITY_AUTO") {
    return (
      `${meta.formula || ""} ` +
      `Based on ${meta.working_days ?? 0} working day(s) - ` +
      `SLA avg ${fmt(meta.sla_avg_pct)}% - ` +
      `${meta.major_error_days ?? 0} Major, ` +
      `${meta.minor_error_days ?? 0} Minor error day(s).`
    );
  }

  if (metric.source_snapshot === "PRODUCTIVITY_AUTO") {
    return (
      `${meta.formula || ""} ` +
      `Based on ${meta.working_days ?? 0} working day(s) - ` +
      `task completion avg ${fmt(meta.task_completion_avg_pct)}%.`
    );
  }

  return meta.formula || null;
}

function initials(name = "") {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "P"
  );
}

function scorePercent(value, max) {
  const score = Number(value);
  const maximum = Number(max);

  if (Number.isNaN(score) || Number.isNaN(maximum) || maximum <= 0) {
    return 0;
  }

  return Math.max(0, Math.min(100, (score / maximum) * 100));
}

function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, "0")}`;
}

function loadTargetAchievementByMonth() {
  try {
    return JSON.parse(
      window.localStorage.getItem(TARGET_ACHIEVEMENT_STORAGE_KEY) || "{}",
    );
  } catch {
    return {};
  }
}

function sameRoundedScore(left, right) {
  const leftScore = roundScore(left);
  const rightScore = roundScore(right);
  return leftScore !== null && rightScore !== null && leftScore === rightScore;
}

/**
 * Copy text with a fallback for browsers/environments where the modern
 * Clipboard API is unavailable or blocked.
 */
async function copyTextToClipboard(text) {
  if (
    navigator.clipboard &&
    typeof navigator.clipboard.writeText === "function"
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Continue to the legacy fallback below.
    }
  }

  const textarea = document.createElement("textarea");

  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  textarea.style.opacity = "0";

  document.body.appendChild(textarea);

  textarea.focus();
  textarea.select();

  try {
    if (!document.execCommand("copy")) {
      throw new Error("Clipboard copy failed");
    }
  } finally {
    document.body.removeChild(textarea);
  }
}

export function PMS({ currentUser, onLogout }) {
  const role = normalizeRole(currentUser?.role);

  const isAdmin = role === "ADMIN";
  const isOpsManager = role === "OPS_MANAGER";
  const isAgent = role === "AGENT";

  const canViewAll = isAdmin || isOpsManager;

  const monthOptions = useMemo(() => buildMonthOptions(), []);
  const [selectedYear, setSelectedYear] = useState(monthOptions[0].year);

  const [selectedMonth, setSelectedMonth] = useState(monthOptions[0].month);
  const [exportFromPeriod, setExportFromPeriod] = useState(() =>
    monthKey(monthOptions[0].year, monthOptions[0].month),
  );
  const [exportToPeriod, setExportToPeriod] = useState(() =>
    monthKey(monthOptions[0].year, monthOptions[0].month),
  );

  const [activeTab, setActiveTab] = useState("monthly");
  const [search, setSearch] = useState("");
  const [targetAchievementByMonth, setTargetAchievementByMonth] = useState(
    loadTargetAchievementByMonth,
  );
  const [targetAchievementDraft, setTargetAchievementDraft] = useState("100");
  const currentTargetAchievementKey = monthKey(selectedYear, selectedMonth);
  const targetAchievementPercent =
    targetAchievementByMonth[currentTargetAchievementKey] ?? 100;

  const [tableData, setTableData] = useState(null);
  const [tableLoading, setTableLoading] = useState(false);
  const [tableError, setTableError] = useState(null);
  const [availablePeriods, setAvailablePeriods] = useState([]);
  const [availablePeriodsLoading, setAvailablePeriodsLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState(null);

  // Employee of the Month has its own loading/error state.
  // Previously every API error was silently converted to eomData=null,
  // making a backend failure look exactly like "no completed PMS records".
  const [eomData, setEomData] = useState(null);
  const [eomLoading, setEomLoading] = useState(false);
  const [eomError, setEomError] = useState(null);

  const [copyState, setCopyState] = useState("idle");

  const [agentRecord, setAgentRecord] = useState(null);
  const [agentLoading, setAgentLoading] = useState(false);

  const [editorUser, setEditorUser] = useState(null);
  const [editorRecord, setEditorRecord] = useState(null);
  const [editorMetrics, setEditorMetrics] = useState([]);
  const [editorRemarks, setEditorRemarks] = useState("");
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorSaving, setEditorSaving] = useState(false);
  const [editorError, setEditorError] = useState(null);
  const [editorRefreshing, setEditorRefreshing] = useState(false);

  const [configItems, setConfigItems] = useState([]);
  const [configTotalWeight, setConfigTotalWeight] = useState(0);
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState(null);
  const [newMetricOpen, setNewMetricOpen] = useState(false);

  const [historyFilters, setHistoryFilters] = useState({
    year: "",
    month: "",
    search: "",
    status: "",
  });

  const [historyData, setHistoryData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [eomStatsData, setEomStatsData] = useState(null);
  const [eomStatsLoading, setEomStatsLoading] = useState(false);
  const [selectedEomEmployeeId, setSelectedEomEmployeeId] = useState("");

  const copyResetRef = useRef(null);

  const leaderboardRows = useMemo(() => {
    const items = (tableData?.items || []).map(adjustedRow);

    return [...items].sort((a, b) => {
      const scoreA = Number(a.final_score) || 0;
      const scoreB = Number(b.final_score) || 0;

      return scoreB - scoreA;
    });
  }, [tableData, targetAchievementPercent]);

  const historyItems = useMemo(
    () => (historyData?.items || []).map(adjustedHistoryRecord),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [historyData, targetAchievementByMonth],
  );

  const visibleHistoryDetail = useMemo(
    () => (historyDetail ? adjustedHistoryRecord(historyDetail) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [historyDetail, targetAchievementByMonth],
  );

  function targetAchievementPercentFor(year, month) {
    return targetAchievementByMonth[monthKey(year, month)] ?? 100;
  }

  function targetAchievementPercentForMetric(metric, year, month) {
    const savedPercent = Number(metric?.calc_meta?.target_percent);

    if (!Number.isNaN(savedPercent)) {
      return clampNumber(savedPercent, 100);
    }

    const finalValue = Number(metric?.final_value);
    const weight = Number(metric?.weight_snapshot);

    if (!Number.isNaN(finalValue) && !Number.isNaN(weight) && weight > 0) {
      return clampNumber((finalValue / weight) * 100, 100);
    }

    return targetAchievementPercentFor(year, month);
  }

  function editorTargetAchievementPercent() {
    const targetMetric = editorMetrics.find(
      (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
    );
    const recordYear = editorRecord?.year ?? selectedYear;
    const recordMonth = editorRecord?.month ?? selectedMonth;

    return targetAchievementPercentForMetric(
      targetMetric,
      recordYear,
      recordMonth,
    );
  }

  function targetMetricValue(metric, percent = targetAchievementPercent) {
    return roundScore(
      clampNumber(
        ((Number(metric.weight_snapshot) || 0) * (Number(percent) || 0)) / 100,
        Number(metric.weight_snapshot) || 0,
      ),
    );
  }

  function metricsFinalScore(metrics) {
    return metrics.reduce(
      (sum, metric) => sum + (Number(metric.final_value) || 0),
      0,
    );
  }

  function metricsMaxScore(metrics) {
    return metrics.reduce(
      (sum, metric) => sum + (Number(metric.weight_snapshot) || 0),
      0,
    );
  }

  function applyTargetAchievement(metrics, percent = targetAchievementPercent) {
    return metrics.map((metric) => {
      if (metric.metric_key !== TARGET_ACHIEVEMENT_KEY) {
        return metric;
      }

      return {
        ...metric,
        final_value: targetMetricValue(metric, percent),
      };
    });
  }

  function adjustedRow(row) {
    const targetMetric = (row.metrics || []).find(
      (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
    );

    if (
      !targetMetric ||
      row.final_score === null ||
      row.final_score === undefined
    ) {
      return row;
    }

    const currentTargetValue = Number(targetMetric.final_value) || 0;
    const sharedTargetValue = targetMetricValue(targetMetric);
    const finalScore = Math.max(
      0,
      (Number(row.final_score) || 0) - currentTargetValue + sharedTargetValue,
    );

    return {
      ...row,
      final_score: finalScore,
      metrics: applyTargetAchievement(row.metrics || []),
    };
  }

  function adjustedHistoryRecord(record) {
    const metrics = record.metrics || [];
    const targetMetric = metrics.find(
      (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
    );

    if (!targetMetric) {
      return record;
    }

    const adjustedMetrics = applyTargetAchievement(
      metrics,
      targetAchievementPercentForMetric(targetMetric, record.year, record.month),
    );
    const finalScore = metricsFinalScore(adjustedMetrics);
    const maximumScore =
      Number(record.maximum_score) || metricsMaxScore(adjustedMetrics);

    return {
      ...record,
      metrics: adjustedMetrics,
      final_score: finalScore,
      maximum_score: maximumScore,
      percentage:
        maximumScore > 0 ? Math.min(100, (finalScore / maximumScore) * 100) : 0,
    };
  }

  function submitTargetAchievement(event) {
    event.preventDefault();
    const nextPercent = clampNumber(targetAchievementDraft, 100);
    setTargetAchievementByMonth((current) => {
      const next = {
        ...current,
        [currentTargetAchievementKey]: nextPercent,
      };
      window.localStorage.setItem(
        TARGET_ACHIEVEMENT_STORAGE_KEY,
        JSON.stringify(next),
      );
      return next;
    });
    setTargetAchievementDraft(String(nextPercent));
  }

  const displayedTopPerformer = useMemo(() => {
    const hasSelectedMonthWinner =
      eomData?.winner &&
      eomData.year === selectedYear &&
      eomData.month === selectedMonth;

    if (hasSelectedMonthWinner) {
      return {
        name: eomData.winner.user_name,
        score: adjustedRow(eomData.winner).final_score,
      };
    }

    const completedRows = leaderboardRows.filter(
      (row) => row.status === "COMPLETED" && row.final_score !== null,
    );
    const topRow = completedRows[0];

    return {
      name: topRow?.user_name || tableData?.top_performer_name || "",
      score: topRow?.final_score ?? tableData?.top_performer_score ?? null,
    };
  }, [eomData, leaderboardRows, selectedMonth, selectedYear, tableData]);

  const roundedTopRows = useMemo(() => {
    const completedRows = leaderboardRows.filter(
      (row) => row.status === "COMPLETED" && row.final_score !== null,
    );
    const topRow = completedRows[0];
    if (!topRow) return [];
    return completedRows.filter((row) =>
      sameRoundedScore(row.final_score, topRow.final_score),
    );
  }, [leaderboardRows]);

  const dashboardInsights = useMemo(() => {
    if (!tableData) {
      return [];
    }

    const items = leaderboardRows;
    const completed = Number(tableData.completed_count) || 0;
    const total = items.length;
    const aboveNinety = items.filter(
      (item) => scorePercent(item.final_score, item.maximum_score) >= 90,
    ).length;

    return [
      `${completed} of ${total} evaluations are completed.`,
      `${aboveNinety} employee${aboveNinety === 1 ? "" : "s"} scored at or above 90%.`,
      displayedTopPerformer.name
        ? `${displayedTopPerformer.name} is the selected top performer.`
        : "No top performer has been published yet.",
    ];
  }, [displayedTopPerformer.name, leaderboardRows, tableData]);

  useEffect(
    () => () => {
      if (copyResetRef.current) {
        window.clearTimeout(copyResetRef.current);
      }
    },
    [],
  );

  // ------------------------------------------------------------------
  // Loaders
  // ------------------------------------------------------------------

  async function loadMonthlyTable() {
    setTableLoading(true);
    setTableError(null);

    try {
      const data = await fetchPmsMonthlyTable({
        year: selectedYear,
        month: selectedMonth,
        search: search || undefined,
      });

      setTableData(data);
    } catch (err) {
      setTableError(err?.message || "Failed to load PMS for this month.");
    } finally {
      setTableLoading(false);
    }
  }

  async function loadAvailablePeriods() {
    if (!canViewAll) {
      setAvailablePeriods([]);
      return;
    }

    setAvailablePeriodsLoading(true);

    try {
      const data = await fetchPmsAvailablePeriods({
        search: search || undefined,
      });
      const items = data.items || [];
      setAvailablePeriods(items);
      setExportFromPeriod((current) =>
        items.some((item) => item.key === current)
          ? current
          : items[items.length - 1]?.key || "",
      );
      setExportToPeriod((current) =>
        items.some((item) => item.key === current)
          ? current
          : items[0]?.key || "",
      );
    } catch {
      setAvailablePeriods([]);
    } finally {
      setAvailablePeriodsLoading(false);
    }
  }

  function parsePeriodKey(value) {
    const [yearValue, monthValue] = String(value || "").split("-");
    return {
      year: Number(yearValue),
      month: Number(monthValue),
    };
  }

  function selectedFiscalYearRange() {
    const startYear = selectedMonth >= 4 ? selectedYear : selectedYear - 1;
    return {
      from: monthKey(startYear, 4),
      to: monthKey(startYear + 1, 3),
    };
  }

  function selectCurrentMonthExportRange() {
    const current = monthKey(selectedYear, selectedMonth);
    if (!availablePeriods.some((item) => item.key === current)) {
      return;
    }
    setExportFromPeriod(current);
    setExportToPeriod(current);
  }

  function selectYearlyExportRange() {
    const range = selectedFiscalYearRange();
    const fiscalPeriods = availablePeriods.filter((item) => {
      const index = item.year * 12 + item.month;
      const from = parsePeriodKey(range.from);
      const to = parsePeriodKey(range.to);
      return index >= from.year * 12 + from.month && index <= to.year * 12 + to.month;
    });
    if (!fiscalPeriods.length) {
      return;
    }
    setExportFromPeriod(fiscalPeriods[fiscalPeriods.length - 1].key);
    setExportToPeriod(fiscalPeriods[0].key);
  }

  function selectAllExportRange() {
    const oldest = availablePeriods[availablePeriods.length - 1];
    const newest = availablePeriods[0];
    if (!oldest || !newest) {
      return;
    }
    setExportFromPeriod(monthKey(oldest.year, oldest.month));
    setExportToPeriod(monthKey(newest.year, newest.month));
  }

  async function handleExportExcel() {
    if (!canViewAll || exportLoading || !availablePeriods.length) {
      return;
    }

    setExportLoading(true);
    setExportError(null);

    try {
      const parsedFromPeriod = parsePeriodKey(exportFromPeriod);
      const parsedToPeriod = parsePeriodKey(exportToPeriod);
      if (
        parsedFromPeriod.year * 12 + parsedFromPeriod.month >
        parsedToPeriod.year * 12 + parsedToPeriod.month
      ) {
        throw new Error("From month must be before or equal to To month.");
      }
      const blob = await exportPmsMonthlyTable({
        from_year: parsedFromPeriod.year,
        from_month: parsedFromPeriod.month,
        to_year: parsedToPeriod.year,
        to_month: parsedToPeriod.month,
        search: search || undefined,
        ...(exportFromPeriod === exportToPeriod &&
        exportFromPeriod === monthKey(selectedYear, selectedMonth)
          ? { target_achievement_percent: targetAchievementPercent }
          : {}),
      });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const fromPeriod = parsePeriodKey(exportFromPeriod);
      const fiscalStart =
        fromPeriod.month >= 4 ? fromPeriod.year : fromPeriod.year - 1;
      link.href = href;
      link.download =
        exportFromPeriod === exportToPeriod
          ? `PMS_Monthly_Data_${fiscalStart}-${String(
              fiscalStart + 1,
            ).slice(-2)}.xlsx`
          : `PMS_Monthly_Data_${exportFromPeriod}_to_${exportToPeriod}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch (err) {
      setExportError(err?.message || "Unable to export PMS data.");
    } finally {
      setExportLoading(false);
    }
  }

  async function loadEmployeeOfMonth() {
    setEomLoading(true);
    setEomError(null);

    try {
      const data = await fetchPmsEmployeeOfMonth({
        year: selectedYear,
        month: selectedMonth,
      });

      setEomData(data);
    } catch (err) {
      setEomData(null);

      // Do not hide a backend/API error behind the "no records" message.
      setEomError(err?.message || "Failed to load Employee of the Month.");
    } finally {
      setEomLoading(false);
    }
  }

  async function loadAgentRecord() {
    if (!isAgent || !currentUser?.id) {
      return;
    }

    setAgentLoading(true);

    try {
      const data = await fetchPmsMonthlyRecord(currentUser.id, {
        year: selectedYear,
        month: selectedMonth,
      });

      setAgentRecord(data);
    } catch {
      setAgentRecord(null);
    } finally {
      setAgentLoading(false);
    }
  }

  async function loadConfig() {
    setConfigLoading(true);
    setConfigError(null);

    try {
      const data = await fetchPmsConfig();

      setConfigItems(data.items || []);

      setConfigTotalWeight(data.total_active_weight || 0);
    } catch (err) {
      setConfigError(err?.message || "Failed to load PMS configuration.");
    } finally {
      setConfigLoading(false);
    }
  }

  async function loadHistory() {
    setHistoryLoading(true);

    try {
      const data = await fetchPmsHistory({
        year: historyFilters.year || undefined,
        month: historyFilters.month || undefined,
        search: historyFilters.search || undefined,
        status: historyFilters.status || undefined,
      });

      setHistoryData(data);
    } catch {
      setHistoryData(null);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadEmployeeOfMonthStats() {
    setEomStatsLoading(true);

    try {
      const data = await fetchPmsEmployeeOfMonthStats();
      setEomStatsData(data);
      setSelectedEomEmployeeId(
        (current) => current || data.items?.[0]?.user_id || "",
      );
    } catch {
      setEomStatsData(null);
    } finally {
      setEomStatsLoading(false);
    }
  }

  useEffect(() => {
    if (canViewAll) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadMonthlyTable();
    }

    loadEmployeeOfMonth();

    if (isAgent) {
      loadAgentRecord();
    }

    // A copy-success message from a previous month should never remain
    // visible after the Admin selects a different month.
    setCopyState("idle");

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear, selectedMonth]);

  useEffect(() => {
    if (!canViewAll) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      loadMonthlyTable();
      loadAvailablePeriods();
    }, 300);

    return () => {
      window.clearTimeout(timeout);
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    if (canViewAll) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadAvailablePeriods();
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canViewAll]);

  useEffect(() => {
    if (activeTab === "config" && isAdmin) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadConfig();
    }

    if (activeTab === "history") {
      loadHistory();
    }

    if (activeTab === "employee-of-month") {
      loadEmployeeOfMonthStats();
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === "history") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadHistory();
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyFilters]);

  useEffect(() => {
    const recordYear = editorRecord?.year ?? selectedYear;
    const recordMonth = editorRecord?.month ?? selectedMonth;
    setEditorMetrics((items) => {
      const targetMetric = items.find(
        (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
      );

      return applyTargetAchievement(
        items,
        targetAchievementPercentForMetric(targetMetric, recordYear, recordMonth),
      );
    });

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetAchievementPercent, editorRecord?.year, editorRecord?.month]);

  useEffect(() => {
    setTargetAchievementDraft(String(targetAchievementPercent));
  }, [targetAchievementPercent]);

  // ------------------------------------------------------------------
  // Editor drawer
  // ------------------------------------------------------------------

  async function openEditor(user, period = {}) {
    const recordYear = period.year ?? selectedYear;
    const recordMonth = period.month ?? selectedMonth;
    setEditorUser(user);
    setEditorError(null);
    setEditorLoading(true);

    try {
      const record = await fetchPmsMonthlyRecord(user.user_id, {
        year: recordYear,
        month: recordMonth,
      });

      setEditorRecord(record);
      const targetMetric = (record.metrics || []).find(
        (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
      );
      const recordTargetPercent = targetAchievementPercentForMetric(
        targetMetric,
        recordYear,
        recordMonth,
      );

      setEditorMetrics(
        applyTargetAchievement(
          record.metrics.map((metric) => ({
            ...metric,
          })),
          recordTargetPercent,
        ),
      );

      setEditorRemarks(record.remarks || "");
    } catch (err) {
      setEditorError(err?.message || "Failed to load this employee's PMS.");
    } finally {
      setEditorLoading(false);
    }
  }

  function closeEditor() {
    setEditorUser(null);
    setEditorRecord(null);
    setEditorMetrics([]);
    setEditorError(null);
  }

  function updateMetricValue(key, value) {
    setEditorMetrics((items) =>
      items.map((item) => {
        if (
          item.metric_key !== key ||
          item.metric_key === TARGET_ACHIEVEMENT_KEY
        ) {
          return item;
        }

        const clamped = clampNumber(value, item.weight_snapshot);

        return {
          ...item,
          final_value: clamped,
        };
      }),
    );
  }

  const editorFinalScore = useMemo(
    () =>
      editorMetrics.reduce(
        (sum, item) => sum + (Number(item.final_value) || 0),
        0,
      ),
    [editorMetrics],
  );

  const editorMaxScore = useMemo(
    () =>
      editorMetrics.reduce(
        (sum, item) => sum + (Number(item.weight_snapshot) || 0),
        0,
      ),
    [editorMetrics],
  );

  async function refreshEditorAutoValues() {
    if (!editorUser) {
      return;
    }

    setEditorRefreshing(true);

    try {
      const recordYear = editorRecord?.year ?? selectedYear;
      const recordMonth = editorRecord?.month ?? selectedMonth;
      const record = await refreshPmsAutoValues({
        user_id: editorUser.user_id,
        year: recordYear,
        month: recordMonth,
      });

      setEditorRecord(record);
      const targetMetric = (record.metrics || []).find(
        (metric) => metric.metric_key === TARGET_ACHIEVEMENT_KEY,
      );
      const recordTargetPercent = targetAchievementPercentForMetric(
        targetMetric,
        recordYear,
        recordMonth,
      );

      setEditorMetrics(
        applyTargetAchievement(
          record.metrics.map((metric) => ({
            ...metric,
          })),
          recordTargetPercent,
        ),
      );
    } catch (err) {
      setEditorError(
        err?.message || "Failed to refresh auto-calculated values.",
      );
    } finally {
      setEditorRefreshing(false);
    }
  }

  async function saveEditor(status) {
    if (!editorUser) {
      return;
    }

    setEditorSaving(true);
    setEditorError(null);

    try {
      const recordYear = editorRecord?.year ?? selectedYear;
      const recordMonth = editorRecord?.month ?? selectedMonth;
      const recordTargetPercent = editorTargetAchievementPercent();
      const payload = {
        user_id: editorUser.user_id,
        year: recordYear,
        month: recordMonth,
        remarks: editorRemarks || null,
        status,
        metrics: editorMetrics.map((metric) => ({
          metric_key: metric.metric_key,
          target_percent:
            metric.metric_key === TARGET_ACHIEVEMENT_KEY
              ? recordTargetPercent
              : undefined,
          final_value:
            metric.metric_key === TARGET_ACHIEVEMENT_KEY
              ? targetMetricValue(metric, recordTargetPercent)
              : Number(metric.final_value) || 0,
        })),
      };

      await savePmsMonthly(payload);

      closeEditor();

      await loadMonthlyTable();
      await loadEmployeeOfMonth();
    } catch (err) {
      setEditorError(err?.message || "Failed to save PMS.");
    } finally {
      setEditorSaving(false);
    }
  }

  // ------------------------------------------------------------------
  // Config
  // ------------------------------------------------------------------

  async function deleteConfigItem(item) {
    const confirmed = window.confirm(
      `Delete "${item.name}" from PMS Configuration?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      await deletePmsConfig(item.id);

      setConfigItems((items) =>
        items.filter((existing) => existing.id !== item.id),
      );

      loadConfig();
    } catch (err) {
      setConfigError(err?.message || "Failed to delete metric.");
    }
  }

  async function saveConfigWeight(item, weight) {
    try {
      const updated = await updatePmsConfig(item.id, {
        weight: Number(weight),
      });

      setConfigItems((items) =>
        items.map((existing) => (existing.id === item.id ? updated : existing)),
      );

      loadConfig();
    } catch (err) {
      setConfigError(err?.message || "Failed to update weight.");
    }
  }

  async function submitNewMetric(event) {
    event.preventDefault();

    const form = event.target;

    const payload = {
      key: form.key.value.trim(),
      name: form.name.value.trim(),
      weight: Number(form.weight.value) || 0,
      source: "MANUAL",
      is_auto_calculated: false,
      is_manually_editable: true,
      is_active: true,
      display_order: configItems.length + 1,
      description: form.description.value.trim() || null,
    };

    try {
      await createPmsConfig(payload);

      setNewMetricOpen(false);

      form.reset();

      loadConfig();
    } catch (err) {
      setConfigError(err?.message || "Failed to create metric.");
    }
  }

  // ------------------------------------------------------------------
  // Employee of the Month
  // ------------------------------------------------------------------

  async function copyEmployeeOfMonth() {
    if (!eomData?.winner) {
      return;
    }

    const winner = adjustedRow(eomData.winner);

    const label = monthLabel(eomData.year, eomData.month);

    const lines = [
      `🏆 Employee of the Month - ${label}`,
      "",
      `Congratulations to ${winner.user_name} for achieving the highest PMS score for ${label}.`,
      "",
      `Final Score: ${fmtScore(winner.final_score)}/${fmtScore(winner.maximum_score)}`,
      "",
      "Performance Breakdown:",
      ...winner.metrics.map(
        (metric) =>
          `- ${metric.metric_name_snapshot}: ${fmtScore(metric.final_value)}/${fmtScore(metric.weight_snapshot)}`,
      ),
      "",
      "Excellent performance and contribution throughout the month.",
    ];

    const text = lines.join("\n");

    try {
      await copyTextToClipboard(text);

      setCopyState("copied");
    } catch {
      setCopyState("failed");
    } finally {
      if (copyResetRef.current) {
        window.clearTimeout(copyResetRef.current);
      }

      copyResetRef.current = window.setTimeout(() => {
        setCopyState("idle");
        copyResetRef.current = null;
      }, 1600);
    }
  }

  async function resolveTie(userId) {
    try {
      const data = await resolvePmsEmployeeOfMonth({
        year: selectedYear,
        month: selectedMonth,
        selected_user_id: userId,
      });

      setEomData(data);
      setEomError(null);
      setCopyState("idle");
    } catch (err) {
      setEomError(err?.message || "Failed to select Employee of the Month.");
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
          const [year, month] = event.target.value.split("-").map(Number);

          setSelectedYear(year);
          setSelectedMonth(month);
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
    );
  }

  function renderSummaryCards() {
    if (!tableData) {
      return null;
    }

    const employeeCount = tableData.items.length;
    const completedPercent = employeeCount
      ? (tableData.completed_count / employeeCount) * 100
      : 0;
    const pendingPercent = employeeCount
      ? (tableData.pending_count / employeeCount) * 100
      : 0;
    const completedRows = leaderboardRows.filter(
      (row) => row.status === "COMPLETED" && row.final_score !== null,
    );
    const adjustedAverageScore = completedRows.length
      ? completedRows.reduce(
          (sum, row) => sum + (Number(row.final_score) || 0),
          0,
        ) / completedRows.length
      : null;
    const averagePercent = scorePercent(
      adjustedAverageScore,
      tableData.total_active_weight || 100,
    );

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
              <i style={{ width: "100%" }} />
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
              {adjustedAverageScore !== null
                ? fmtScore(adjustedAverageScore)
                : "-"}
            </strong>
            <div className="pmsModule-mini-meter">
              <i style={{ width: `${averagePercent}%` }} />
            </div>
          </div>

          <div className="pmsModule-summary-card pmsModule-summary-card-highlight">
            <span>Top Performer</span>
            <strong>{displayedTopPerformer.name || "-"}</strong>
            {displayedTopPerformer.score !== null ? (
              <small>{fmtScore(displayedTopPerformer.score)}</small>
            ) : null}
          </div>
        </div>

        {tableData.total_active_weight !== 100 ? (
          <div className="pmsModule-summary-card pmsModule-summary-card-warning">
            <span>Configured Total Weight</span>
            <strong>{fmtScore(tableData.total_active_weight)}</strong>
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
    );
  }
  function renderEmployeeOfMonth() {
    if (eomLoading) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-empty pmsModule-skeleton-panel">
          <div className="pmsModule-award-outline" />
          <div>
            <h3>Winner Spotlight</h3>
            <p>
              Loading Employee of the Month for{" "}
              {monthLabel(selectedYear, selectedMonth)}...
            </p>
          </div>
        </section>
      );
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
      );
    }

    if (
      !eomData ||
      (!eomData.winner && !eomData.is_tie && roundedTopRows.length < 2)
    ) {
      return (
        <section className="pmsModule-eom-card pmsModule-eom-empty">
          <div className="pmsModule-award-outline" />
          <div>
            <h3>Winner Spotlight</h3>
            <p>
              No completed PMS records yet for{" "}
              {monthLabel(selectedYear, selectedMonth)}.
            </p>
          </div>
        </section>
      );
    }

    if (
      (eomData.is_tie && !eomData.winner) ||
      (roundedTopRows.length > 1 && !eomData?.winner)
    ) {
      const candidates =
        roundedTopRows.length > 1 ? roundedTopRows : eomData.candidates;
      return (
        <section className="pmsModule-eom-card pmsModule-eom-tie">
          <div className="pmsModule-eom-copy">
            <span className="pmsModule-eyebrow">Winner Decision</span>
            <h3>Joint Top Performers</h3>
            <p>
              {candidates.length} employees are tied for the highest rounded
              score this month.
            </p>
          </div>

          <ul className="pmsModule-eom-tie-list">
            {candidates.map((candidate) => (
              <li key={candidate.user_id}>
                <span>{candidate.user_name}</span>
                <strong>{fmtScore(candidate.final_score)}</strong>

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
      );
    }

    const winner = eomData.winner;
    const percent = scorePercent(winner.final_score, winner.maximum_score);

    return (
      <section className="pmsModule-eom-card pmsModule-winner-spotlight">
        <div className="pmsModule-eom-copy">
          <span className="pmsModule-eyebrow">
            Employee of the Month{eomData.is_tie ? " - tie resolved" : ""}
          </span>

          <div className="pmsModule-winner-identity">
            <div className="pmsModule-avatar">{initials(winner.user_name)}</div>

            <div>
              <h3>{winner.user_name}</h3>
              <p>Final PMS Score</p>
            </div>
          </div>

          <div className="pmsModule-eom-score">
            <strong>{fmtScore(winner.final_score)}</strong>
            <span>/ {fmtScore(winner.maximum_score)}</span>
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
              className={`secondary-button ${copyState === "copied" ? "pmsModule-button-success" : ""}`}
              onClick={copyEmployeeOfMonth}
            >
              <Icon name={copyState === "copied" ? "activate" : "copy"} />
              {copyState === "copied" ? "Copied" : "Copy to Clipboard"}
            </button>

            {copyState === "failed" ? (
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
            );

            return (
              <div key={metric.metric_key}>
                <span>{metric.metric_name_snapshot}</span>
                <strong>
                  {fmtScore(metric.final_value)} /{" "}
                  {fmtScore(metric.weight_snapshot)}
                </strong>
                <div className="pmsModule-metric-bar">
                  <i style={{ width: `${metricPercent}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    );
  }
  function renderMonthlyTable() {
    if (tableLoading) {
      return (
        <div className="pmsModule-empty-state pmsModule-skeleton-panel">
          Loading PMS for {monthLabel(selectedYear, selectedMonth)}...
        </div>
      );
    }

    if (tableError) {
      return <div className="pmsModule-empty-state error">{tableError}</div>;
    }

    if (!tableData || tableData.items.length === 0) {
      return (
        <div className="pmsModule-empty-state">
          No PMS-eligible employees found{search ? " for that search." : "."}
        </div>
      );
    }

    return (
      <section className="pmsModule-leaderboard">
        <div className="pmsModule-section-heading">
          <div>
            <span className="pmsModule-eyebrow">Leaderboard</span>
            <h2>Employee Performance Ranking</h2>
          </div>
          <div className="pmsModule-leaderboard-controls">
            {isAdmin ? (
              <form
                className="pmsModule-target-achievement-field"
                onSubmit={submitTargetAchievement}
              >
                <label htmlFor="pms-target-achievement">
                  Target Achievement
                </label>
                <input
                  id="pms-target-achievement"
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={targetAchievementDraft}
                  onChange={(event) =>
                    setTargetAchievementDraft(event.target.value)
                  }
                />
                <strong>%</strong>
                <button
                  type="submit"
                  className="secondary-button-compact-action action-button action-upload"
                >
                  Submit
                </button>
              </form>
            ) : null}
            <small>{leaderboardRows.length} employees</small>
          </div>
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
                );
                const rank = index + 1;

                return (
                  <tr
                    key={row.user_id}
                    className={rank <= 3 ? `pmsModule-rank-${rank}` : ""}
                  >
                    <td>
                      <span className="pmsModule-rank-badge">{rank}</span>
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
                            ? `${fmtScore(row.final_score)} / ${fmtScore(row.maximum_score)}`
                            : "-"}
                        </strong>
                        <div className="pmsModule-score-track">
                          <i style={{ width: `${percent}%` }} />
                        </div>
                      </div>
                    </td>

                    <td>
                      <span
                        className={statusBadgeClass(row.status || "PENDING")}
                      >
                        {row.status || "Not started"}
                      </span>
                    </td>

                    <td>
                      {isAdmin ? (
                        <button
                          type="button"
                          className="secondary-button compact-action action-button action-edit"
                          onClick={() => openEditor(row)}
                        >
                          {row.record_id ? "Edit PMS" : "Enter PMS"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="secondary-button compact-action action-button action-load"
                          onClick={() => openEditor(row)}
                          disabled={!row.record_id}
                        >
                          View
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    );
  }
  function renderEditorDrawer() {
    if (!editorUser) {
      return null;
    }

    return (
      <div className="drawer-backdrop" onClick={closeEditor}>
        <div
          className="modal-panel pmsModule-editor-drawer"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="drawer-header">
            <div>
              <strong>{editorUser.user_name}</strong>

              <p>{monthLabel(selectedYear, selectedMonth)}</p>
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
            <div className="pmsModule-empty-state">Loading...</div>
          ) : (
            <>
              {editorError ? (
                <div className="form-message error">{editorError}</div>
              ) : null}

              <div className="pmsModule-editor-metrics">
                {editorMetrics.map((metric) => {
                  const isAuto = metric.is_auto_calculated_snapshot;
                  const isTargetAchievement =
                    metric.metric_key === TARGET_ACHIEVEMENT_KEY;

                  const tooltip = metricTooltip(metric);

                  const overridden =
                    isAuto &&
                    Number(metric.final_value) !== Number(metric.auto_value);

                  return (
                    <div
                      className="pmsModule-editor-metric-row"
                      key={metric.metric_key}
                    >
                      <div className="pmsModule-editor-metric-label">
                        <div className="pmsModule-editor-metric-title">
                          <strong>{metric.metric_name_snapshot}</strong>

                          {isAuto ? (
                            <span
                              className={`source-badge ${
                                overridden ? "source-manual" : "source-auto"
                              }`}
                            >
                              {overridden ? "OVERRIDDEN" : "AUTO"}
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
                            Auto calculated:{" "}
                            {metric.auto_value !== null
                              ? fmtScore(metric.auto_value)
                              : "-"}
                            {" / "}
                            {fmtScore(metric.weight_snapshot)}
                          </small>
                        ) : isTargetAchievement ? (
                          <small className="pmsModule-auto-value">
                            Shared target: {fmt(
                              editorTargetAchievementPercent(),
                            )}
                            % of{" "}
                            {fmtScore(metric.weight_snapshot)}
                          </small>
                        ) : null}
                      </div>

                      <div className="pmsModule-editor-metric-score">
                        <input
                          type="number"
                          min={0}
                          max={metric.weight_snapshot}
                          step="0.1"
                          disabled={isTargetAchievement}
                          value={metric.final_value}
                          onChange={(event) =>
                            updateMetricValue(
                              metric.metric_key,
                              event.target.value,
                            )
                          }
                        />

                        <span className="pmsModule-score-max">
                          / {fmtScore(metric.weight_snapshot)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="pmsModule-editor-final-row">
                <span>Final Score</span>

                <strong>
                  {fmtScore(editorFinalScore)}
                  {" / "}
                  {fmtScore(editorMaxScore)}
                </strong>
              </div>

              <div className="field">
                <label htmlFor="pms-remarks">Remarks</label>

                <textarea
                  id="pms-remarks"
                  value={editorRemarks}
                  onChange={(event) => setEditorRemarks(event.target.value)}
                  rows={3}
                />
              </div>

              {isAdmin ? (
                <div className="modal-actions pmsModule-editor-actions">
                  <button
                    type="button"
                    className="secondary-button action-button action-refresh"
                    onClick={refreshEditorAutoValues}
                    disabled={editorRefreshing}
                  >
                    <Icon name="refresh" />{" "}
                    {editorRefreshing ? "Refreshing..." : "Refresh Auto Values"}
                  </button>

                  <div className="pmsModule-editor-save-group">
                    <button
                      type="button"
                      className="secondary-button action-button action-save"
                      onClick={() => saveEditor("DRAFT")}
                      disabled={editorSaving}
                    >
                      Save as Draft
                    </button>

                    <button
                      type="button"
                      className="primary-button action-button action-upload"
                      onClick={() => saveEditor("COMPLETED")}
                      disabled={editorSaving}
                    >
                      {editorSaving ? "Saving..." : "Save PMS"}
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
    );
  }

  function renderConfigTab() {
    if (!isAdmin) {
      return (
        <div className="pmsModule-empty-state">
          Only Admins can manage PMS configuration.
        </div>
      );
    }

    return (
      <div className="pmsModule-config-card">
        {configError ? (
          <div className="form-message error">{configError}</div>
        ) : null}

        {configLoading ? (
          <div className="pmsModule-empty-state">Loading configuration...</div>
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
                  {configItems.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.name}</strong>

                        {item.description ? (
                          <small className="pmsModule-table-subtext">
                            {item.description}
                          </small>
                        ) : null}
                      </td>

                      <td>
                        {item.source === "MANUAL"
                          ? "Manual"
                          : item.source === "PRODUCTIVITY_AUTO"
                            ? "Productivity (Daily Data)"
                            : item.source === "QUALITY_AUTO"
                              ? "Quality (Daily Data)"
                              : "Custom"}
                      </td>

                      <td>
                        <input
                          type="number"
                          min={0}
                          className="pmsModule-config-weight-input"
                          defaultValue={item.weight}
                          onBlur={(event) => {
                            if (Number(event.target.value) !== item.weight) {
                              saveConfigWeight(item, event.target.value);
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
                  ))}
                </tbody>

                <tfoot>
                  <tr>
                    <td colSpan={2}>
                      <strong>Total Weight (active)</strong>
                    </td>

                    <td colSpan={2}>
                      <strong>
                        {fmt(configTotalWeight)}
                        {configTotalWeight !== 100 ? " warning not 100" : ""}
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
                      <label htmlFor="metric-key">Key</label>

                      <input
                        id="metric-key"
                        name="key"
                        placeholder="e.g. teamwork"
                        required
                      />
                    </div>

                    <div className="field">
                      <label htmlFor="metric-name">Name</label>

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
                      <label htmlFor="metric-weight">Weight</label>

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
                      <label htmlFor="metric-description">Description</label>

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
                      onClick={() => setNewMetricOpen(false)}
                    >
                      Cancel
                    </button>

                    <button type="submit" className="primary-button">
                      Add Metric
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setNewMetricOpen(true)}
                >
                  + Add Metric
                </button>
              )}
            </div>

            <p className="pmsModule-config-note">
              New auto-calculated metrics (Productivity/Quality-style)
              aren&apos;t available from this form yet - only Manual metrics can
              be added here. Deactivating a metric hides it from future months
              without touching any historical PMS record.
            </p>
          </>
        )}
      </div>
    );
  }

  function renderHistoryTab() {
    return (
      <div className="pms-history-card">
        <div className="dailyEntry-history-filters pmsModule-history-filters">
          <div className="field">
            <label htmlFor="history-year">Year</label>

            <input
              id="history-year"
              type="number"
              value={historyFilters.year}
              onChange={(event) =>
                setHistoryFilters((filters) => ({
                  ...filters,
                  year: event.target.value,
                }))
              }
              placeholder="e.g. 2026"
            />
          </div>

          <div className="field">
            <label htmlFor="history-month">Month</label>

            <select
              id="history-month"
              value={historyFilters.month}
              onChange={(event) =>
                setHistoryFilters((filters) => ({
                  ...filters,
                  month: event.target.value,
                }))
              }
            >
              <option value="">All</option>

              {MONTH_NAMES.map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {canViewAll ? (
            <div className="field">
              <label htmlFor="history-search">Employee</label>

              <input
                id="history-search"
                value={historyFilters.search}
                onChange={(event) =>
                  setHistoryFilters((filters) => ({
                    ...filters,
                    search: event.target.value,
                  }))
                }
                placeholder="Search name..."
              />
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="history-status">Status</label>

            <select
              id="history-status"
              value={historyFilters.status}
              onChange={(event) =>
                setHistoryFilters((filters) => ({
                  ...filters,
                  status: event.target.value,
                }))
              }
            >
              <option value="">All</option>

              <option value="COMPLETED">Completed</option>

              <option value="DRAFT">Draft</option>
            </select>
          </div>
        </div>

        {historyLoading ? (
          <div className="pmsModule-empty-state">Loading history...</div>
        ) : !historyData || historyItems.length === 0 ? (
          <div className="pmsModule-empty-state">
            No PMS history matches these filters.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Month</th>

                  {canViewAll ? <th>Employee</th> : null}

                  <th>Final Score</th>
                  <th>Percentage</th>
                  <th>Status</th>
                  <th>Last Updated</th>
                </tr>
              </thead>

              <tbody>
                {historyItems.map((item) => (
                  <tr
                    key={item.record_id}
                    onClick={() => setHistoryDetail(item)}
                  >
                    <td>{monthLabel(item.year, item.month)}</td>

                    {canViewAll ? <td>{item.user_name}</td> : null}

                    <td>
                      {fmtScore(item.final_score)}
                      {" / "}
                      {fmtScore(item.maximum_score)}
                    </td>

                    <td>{fmt(item.percentage)}%</td>

                    <td>
                      <span className={statusBadgeClass(item.status)}>
                        {item.status}
                      </span>
                    </td>

                    <td>{new Date(item.updated_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {visibleHistoryDetail ? (
          <div
            className="modal-backdrop"
            onClick={() => setHistoryDetail(null)}
          >
            <div
              className="modal-panel"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="drawer-header">
                <div>
                  <strong>{visibleHistoryDetail.user_name}</strong>

                  <p>
                    {monthLabel(
                      visibleHistoryDetail.year,
                      visibleHistoryDetail.month,
                    )}
                  </p>
                </div>

                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setHistoryDetail(null)}
                  aria-label="Close"
                >
                  <Icon name="close" />
                </button>
              </div>

              <p>
                Final Score:{" "}
                <strong>
                  {fmtScore(visibleHistoryDetail.final_score)}
                  {" / "}
                  {fmtScore(visibleHistoryDetail.maximum_score)}
                </strong>
                {" ("}
                {fmt(visibleHistoryDetail.percentage)}
                %)
              </p>

              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setHistoryDetail(null);

                  setSelectedYear(visibleHistoryDetail.year);

                  setSelectedMonth(visibleHistoryDetail.month);

                  openEditor(
                    {
                      user_id: visibleHistoryDetail.user_id,
                      user_name: visibleHistoryDetail.user_name,
                    },
                    {
                      year: visibleHistoryDetail.year,
                      month: visibleHistoryDetail.month,
                    },
                  );
                }}
              >
                View Full Breakdown
              </button>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderEmployeeOfMonthTab() {
    const items = eomStatsData?.items || [];
    const selectedEmployee =
      items.find((item) => item.user_id === selectedEomEmployeeId) ||
      items[0] ||
      null;

    return (
      <div className="pms-history-card pmsModule-eom-stats-card">
        <div className="pmsModule-section-heading">
          <div>
            <span className="pmsModule-eyebrow">Employee of the Month</span>
            <h2>Winner History</h2>
          </div>
          <small>{items.length} employees</small>
        </div>

        {eomStatsLoading ? (
          <div className="pmsModule-empty-state pmsModule-skeleton-panel">
            Loading Employee of the Month history...
          </div>
        ) : items.length === 0 ? (
          <div className="pmsModule-empty-state">
            No Employee of the Month winners have been selected yet.
          </div>
        ) : (
          <div className="pmsModule-eom-stats-layout">
            <div className="pmsModule-eom-stats-grid">
              {items.map((item) => (
                <button
                  type="button"
                  className={`pmsModule-eom-stat-card${item.user_id === selectedEmployee?.user_id ? " active" : ""}`}
                  key={item.user_id}
                  onClick={() => setSelectedEomEmployeeId(item.user_id)}
                >
                  <span className="pmsModule-avatar pmsModule-avatar-small">
                    {initials(item.user_name)}
                  </span>
                  <span>
                    <strong>{item.user_name}</strong>
                    {item.user_email ? <small>{item.user_email}</small> : null}
                  </span>
                  <b>{item.win_count}</b>
                </button>
              ))}
            </div>

            <div className="pmsModule-eom-win-list">
              <div className="pmsModule-eom-win-list-header">
                <strong>{selectedEmployee?.user_name}</strong>
                <span>{selectedEmployee?.win_count || 0} wins</span>
              </div>
              {(selectedEmployee?.wins || []).map((win) => (
                <div
                  className="pmsModule-eom-win-row"
                  key={`${win.year}-${win.month}`}
                >
                  <span>{monthLabel(win.year, win.month)}</span>
                  <strong>{fmtScore(win.final_score)}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderAgentOwnRecord() {
    if (agentLoading) {
      return <div className="pmsModule-empty-state">Loading your PMS...</div>;
    }

    if (!agentRecord || !agentRecord.id) {
      return (
        <div className="pmsModule-empty-state">
          Your PMS for {monthLabel(selectedYear, selectedMonth)} has not been
          published yet.
        </div>
      );
    }

    return (
      <div className="pms-entry-card pmsModule-agent-record">
        <div className="pmsModule-editor-final-row">
          <span>Final Score</span>

          <strong>
            {fmtScore(agentRecord.final_score)}
            {" / "}
            {fmtScore(agentRecord.maximum_score)}
          </strong>
        </div>

        <div className="pmsModule-editor-metrics">
          {agentRecord.metrics.map((metric) => (
            <div
              className="pmsModule-editor-metric-row"
              key={metric.metric_key}
            >
              <div className="pmsModule-editor-metric-label">
                <strong>{metric.metric_name_snapshot}</strong>
              </div>

              <div className="pmsModule-editor-metric-score">
                <span>
                  {fmtScore(metric.final_value)}
                  {" / "}
                  {fmtScore(metric.weight_snapshot)}
                </span>
              </div>
            </div>
          ))}
        </div>

        {agentRecord.remarks ? (
          <p className="pmsModule-remarks-readout">
            Remarks: {agentRecord.remarks}
          </p>
        ) : null}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Main render
  // ------------------------------------------------------------------

  return (
    <AppLayout activePage="PMS" currentUser={currentUser} onLogout={onLogout}>
      <div className="pmsModule-page">
        <div className="page-header pmsModule-header">
          <div className="pmsModule-header-content">
            <span className="pmsModule-eyebrow">
              Performance Intelligence Center
            </span>

            <h1>PMS</h1>

            <p>Monitor achievement, productivity and team performance.</p>

            <div className="pmsModule-header-stats">
              <span>{monthLabel(selectedYear, selectedMonth)}</span>
              <span>
                {canViewAll
                  ? `${leaderboardRows.length} employees`
                  : "Personal view"}
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
                onChange={(event) => setSearch(event.target.value)}
              />
            ) : null}

            {canViewAll ? (
              <div className="pmsModule-export-controls">
                <label>
                  <span>From</span>
                  <select
                    value={exportFromPeriod}
                    onChange={(event) => setExportFromPeriod(event.target.value)}
                    disabled={availablePeriodsLoading || !availablePeriods.length}
                  >
                    {availablePeriods.map((option) => (
                      <option
                        key={`from-${option.year}-${option.month}`}
                        value={monthKey(option.year, option.month)}
                      >
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>To</span>
                  <select
                    value={exportToPeriod}
                    onChange={(event) => setExportToPeriod(event.target.value)}
                    disabled={availablePeriodsLoading || !availablePeriods.length}
                  >
                    {availablePeriods.map((option) => (
                      <option
                        key={`to-${option.year}-${option.month}`}
                        value={monthKey(option.year, option.month)}
                      >
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>

                <button
                  type="button"
                  className="secondary-button compact-action"
                  onClick={selectCurrentMonthExportRange}
                  disabled={
                    !availablePeriods.some(
                      (item) => item.key === monthKey(selectedYear, selectedMonth),
                    )
                  }
                >
                  Current
                </button>

                <button
                  type="button"
                  className="secondary-button compact-action"
                  onClick={selectYearlyExportRange}
                  disabled={!availablePeriods.length}
                >
                  Yearly
                </button>

                <button
                  type="button"
                  className="secondary-button compact-action"
                  onClick={selectAllExportRange}
                  disabled={!availablePeriods.length}
                >
                  All
                </button>

                <button
                  type="button"
                  className="secondary-button compact-action action-button action-export"
                  onClick={handleExportExcel}
                  disabled={exportLoading || availablePeriodsLoading || !availablePeriods.length}
                >
                  <Icon name="download" />
                  {exportLoading
                    ? "Exporting..."
                    : availablePeriodsLoading
                      ? "Loading..."
                      : "Export Excel"}
                </button>
              </div>
            ) : null}
          </div>
        </div>

        {exportError ? (
          <div className="form-message error">{exportError}</div>
        ) : null}

        <nav className="pmsModule-tabs">
          <button
            type="button"
            className={activeTab === "monthly" ? "active" : ""}
            onClick={() => setActiveTab("monthly")}
          >
            Monthly
          </button>

          <button
            type="button"
            className={activeTab === "history" ? "active" : ""}
            onClick={() => setActiveTab("history")}
          >
            History
          </button>

          {canViewAll ? (
            <button
              type="button"
              className={activeTab === "employee-of-month" ? "active" : ""}
              onClick={() => setActiveTab("employee-of-month")}
            >
              Employee of the Month
            </button>
          ) : null}

          {isAdmin ? (
            <button
              type="button"
              className={activeTab === "config" ? "active" : ""}
              onClick={() => setActiveTab("config")}
            >
              PMS Configuration
            </button>
          ) : null}
        </nav>

        {activeTab === "monthly" ? (
          <>
            {canViewAll ? (
              <>
                {renderEmployeeOfMonth()}

                {renderSummaryCards()}

                <div className="pms-history-card">{renderMonthlyTable()}</div>
              </>
            ) : (
              renderAgentOwnRecord()
            )}
          </>
        ) : null}

        {activeTab === "history" ? renderHistoryTab() : null}

        {activeTab === "employee-of-month" ? renderEmployeeOfMonthTab() : null}

        {activeTab === "config" ? renderConfigTab() : null}

        {renderEditorDrawer()}
      </div>
    </AppLayout>
  );
}

export default PMS;

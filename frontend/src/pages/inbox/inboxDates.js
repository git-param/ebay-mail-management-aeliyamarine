/**
 * Formats the browser's local calendar date as YYYY-MM-DD.
 *
 * This intentionally avoids toISOString because converting local midnight to
 * UTC can shift the date backward in time zones such as Asia/Kolkata.
 *
 * @param {Date} date
 * @returns {string}
 */
export function isoDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

/**
 * Adds one local calendar day to a YYYY-MM-DD value.
 *
 * The inbox UI treats the custom "To" date as inclusive while the backend
 * repository uses an exclusive upper bound.
 *
 * @param {string} value
 * @returns {string}
 */
export function addOneDayToIsoDate(value) {
  if (!value) {
    return value
  }

  const [year, month, day] = value.split('-').map(Number)

  if (!year || !month || !day) {
    return value
  }

  const date = new Date(year, month - 1, day)
  date.setDate(date.getDate() + 1)

  return isoDate(date)
}

/**
 * Returns the date range associated with an inbox period filter.
 *
 * Both dates are inclusive calendar days in the UI. Request conversion
 * creates the exclusive timestamp upper bound exactly once.
 *
 * @param {string} period
 * @returns {{date_from?: string, date_to?: string}}
 */
export function periodRange(period, now = new Date()) {
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  )

  if (period === 'all') {
    return {
      date_from: '',
      date_to: '',
    }
  }

  if (period === 'custom') {
    return {}
  }

  if (period === 'today') {
    return {
      date_from: isoDate(todayStart),
      date_to: isoDate(todayStart),
    }
  }

  if (period === 'yesterday') {
    const yesterdayStart = new Date(todayStart)
    yesterdayStart.setDate(yesterdayStart.getDate() - 1)

    return {
      date_from: isoDate(yesterdayStart),
      date_to: isoDate(yesterdayStart),
    }
  }

  const start = new Date(todayStart)

  if (period === 'week') {
    start.setDate(start.getDate() - start.getDay())
  } else if (period === 'month') {
    start.setDate(1)
  } else if (period === 'year') {
    start.setMonth(0)
    start.setDate(1)
  } else {
    start.setDate(start.getDate() - (Number(period) || 90) + 1)
  }

  return {
    date_from: isoDate(start),
    date_to: isoDate(todayStart),
  }
}

/** Build exclusive UTC bounds from the browser's local calendar dates. */
export function inboxRequestFilters(filters) {
  const { period, ...request } = filters
  const range = period === 'custom' ? request : periodRange(period || 'all')
  if (range.date_from && range.date_to && range.date_from > range.date_to) {
    throw new Error('From date must be on or before To date.')
  }
  const localMidnight = (value) => {
    const [year, month, day] = value.split('-').map(Number)
    return new Date(year, month - 1, day).toISOString()
  }
  request.date_from = range.date_from ? localMidnight(range.date_from) : ''
  const end = addOneDayToIsoDate(range.date_to)
  request.date_to = end ? localMidnight(end) : ''
  return request
}

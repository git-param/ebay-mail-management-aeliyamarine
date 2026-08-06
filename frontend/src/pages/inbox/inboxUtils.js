export { default } from './Dashboard'

export const DEFAULT_PAGE_SIZE = 20

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

export const STATUSES = ['OPEN', 'PENDING', 'RESOLVED', 'CLOSED']

export const LIST_WIDTH_KEY = 'inboxListPanelWidth'

export const DETAILS_WIDTH_KEY = 'inboxDetailsPanelWidth'

export const SHOW_MESSAGE_ATTACHMENTS = true

export const PERIOD_OPTIONS = [
  ['all', 'All time'],
  ['today', 'Today'],
  ['yesterday', 'Yesterday'],
  ['90', 'Last 90 days'],
  ['60', 'Last 60 days'],
  ['30', 'Last 30 days'],
  ['week', 'This week'],
  ['month', 'This month'],
  ['year', 'This year'],
  ['custom', 'Custom'],
]

/**
 * Reads a numeric value from localStorage.
 *
 * @param {string} key
 * @param {number} fallback
 * @returns {number}
 */
export function getStoredNumber(key, fallback) {
  const value = Number(localStorage.getItem(key))
  return Number.isFinite(value) ? value : fallback
}

/**
 * Returns the selected conversation ID from the browser URL.
 *
 * @returns {string}
 */
export function getConversationIdFromUrl() {
  return new URLSearchParams(window.location.search).get('conversation_id') || ''
}

/**
 * Restricts a number to the supplied range.
 *
 * @param {number} value
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

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
 * The returned date_to value is exclusive because the backend filters using
 * sent_at < date_to.
 *
 * @param {string} period
 * @returns {{date_from?: string, date_to?: string}}
 */
export function periodRange(period) {
  const now = new Date()
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  )

  const tomorrowStart = new Date(todayStart)
  tomorrowStart.setDate(tomorrowStart.getDate() + 1)

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
      date_to: isoDate(tomorrowStart),
    }
  }

  if (period === 'yesterday') {
    const yesterdayStart = new Date(todayStart)
    yesterdayStart.setDate(yesterdayStart.getDate() - 1)

    return {
      date_from: isoDate(yesterdayStart),
      date_to: isoDate(todayStart),
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
    date_to: isoDate(tomorrowStart),
  }
}

/**
 * Formats a date/time value for display.
 *
 * @param {string|Date|null|undefined} value
 * @returns {string}
 */
export function formatDate(value) {
  if (!value) {
    return 'Not available'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Formats a deadline relative to the current time.
 *
 * @param {string|Date|null|undefined} value
 * @returns {string}
 */
export function formatRelativeDeadline(value) {
  if (!value) {
    return 'No deadline'
  }

  const due = new Date(value)

  if (Number.isNaN(due.getTime())) {
    return String(value)
  }

  const diffMs = due.getTime() - Date.now()
  const absoluteHours = Math.abs(diffMs) / 36e5

  if (diffMs < 0) {
    return absoluteHours < 1
      ? 'Overdue'
      : `${Math.ceil(absoluteHours)}h overdue`
  }

  if (absoluteHours < 1) {
    return 'Due soon'
  }

  return `${Math.ceil(absoluteHours)}h left`
}

/**
 * Returns the visual tone for a deadline.
 *
 * @param {string|Date|null|undefined} value
 * @returns {'neutral'|'danger'|'warning'|'good'}
 */
export function deadlineTone(value) {
  if (!value) {
    return 'neutral'
  }

  const timestamp = new Date(value).getTime()

  if (Number.isNaN(timestamp)) {
    return 'neutral'
  }

  const diffMs = timestamp - Date.now()

  if (diffMs < 0) {
    return 'danger'
  }

  if (diffMs < 4 * 36e5) {
    return 'warning'
  }

  return 'good'
}

/**
 * Formats an SLA duration supplied in seconds.
 *
 * @param {number|string|null|undefined} seconds
 * @returns {string}
 */
export function formatSlaDuration(seconds) {
  const totalMinutes = Math.max(
    0,
    Math.round(Number(seconds || 0) / 60),
  )

  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  if (hours && minutes) {
    return `${hours}h ${String(minutes).padStart(2, '0')}m`
  }

  if (hours) {
    return `${hours}h`
  }

  return `${minutes}m`
}

/**
 * Returns the SLA badge tone for a conversation.
 *
 * @param {object} conversation
 * @returns {'neutral'|'danger'|'warning'|'good'}
 */
export function slaTone(conversation) {
  if (conversation?.sla_response_seconds != null) {
    return conversation.sla_met === false ? 'danger' : 'good'
  }

  if (conversation?.sla_elapsed_seconds != null) {
    return conversation.sla_status === 'OVERDUE'
      ? 'danger'
      : 'warning'
  }

  return 'neutral'
}

/**
 * Returns the main SLA duration label.
 *
 * @param {object} conversation
 * @returns {string}
 */
export function slaLabel(conversation) {
  if (conversation?.sla_response_seconds != null) {
    return formatSlaDuration(conversation.sla_response_seconds)
  }

  if (conversation?.sla_elapsed_seconds != null) {
    return formatSlaDuration(conversation.sla_elapsed_seconds)
  }

  return 'No SLA'
}

/**
 * Returns the supporting SLA caption.
 *
 * @param {object} conversation
 * @returns {string}
 */
export function slaCaption(conversation) {
  if (conversation?.sla_response_seconds != null) {
    return 'Responded in'
  }

  if (conversation?.sla_elapsed_seconds != null) {
    return 'Pending'
  }

  return 'SLA'
}

/**
 * Converts a backend user into the shape used by inbox controls.
 *
 * @param {object} user
 * @returns {{
 *   id: string,
 *   fullName: string,
 *   email: string,
 *   role: string,
 *   isActive: boolean
 * }}
 */
export function normalizeUser(user) {
  return {
    id: user.id,
    fullName:
      user.full_name ||
      user.name ||
      user.fullName ||
      user.email ||
      'Unknown user',
    email: user.email || '',
    role: user.role || '',
    isActive: user.is_active !== false,
  }
}

/**
 * Converts a backend category into the inbox category shape.
 *
 * @param {object} category
 * @returns {{
 *   id: string,
 *   name: string,
 *   color: string,
 *   isActive: boolean
 * }}
 */
export function normalizeCategory(category) {
  return {
    id: category.id,
    name: category.name,
    color: category.color || '#2563eb',
    isActive: category.is_active !== false,
  }
}

/**
 * Converts an eBay account into the inbox account dropdown shape.
 *
 * @param {object} account
 * @returns {{id: string, label: string}}
 */
export function normalizeAccount(account) {
  return {
    id: account.id,
    label:
      account.ebay_username ||
      account.account_name ||
      account.id,
  }
}

/**
 * Returns a readable conversation source label.
 *
 * @param {string} value
 * @returns {string}
 */
export function conversationTypeLabel(value) {
  const labels = {
    FROM_MEMBERS: 'From members',
    FROM_EBAY: 'From eBay',
  }

  return labels[value] || value || 'Unknown source'
}

/**
 * Indicates whether the conversation was generated by eBay.
 *
 * @param {object|null|undefined} conversation
 * @returns {boolean}
 */
export function isEbaySystemConversation(conversation) {
  return conversation?.provider_conversation_type === 'FROM_EBAY'
}

/**
 * Performs a simple check for HTML message content.
 *
 * @param {string|null|undefined} value
 * @returns {boolean}
 */
export function isHtmlBody(value) {
  return /<\/?[a-z][\s\S]*>/i.test(value || '')
}

/**
 * Extracts an array from common API response shapes.
 *
 * @param {unknown} response
 * @returns {Array}
 */
export function getList(response) {
  if (Array.isArray(response)) {
    return response
  }

  if (!response || typeof response !== 'object') {
    return []
  }

  return (
    response.items ||
    response.data ||
    response.users ||
    response.categories ||
    []
  )
}

/**
 * Builds up to two initials from a name.
 *
 * @param {string|null|undefined} name
 * @returns {string}
 */
export function getInitials(name) {
  return String(name || 'U')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/**
 * Returns a readable user label.
 *
 * @param {object|null|undefined} user
 * @returns {string}
 */
export function userLabel(user) {
  if (!user) {
    return 'Unassigned'
  }

  return (
    user.full_name ||
    user.name ||
    user.fullName ||
    user.email ||
    'Unknown user'
  )
}

/**
 * Returns the best available preview text for a conversation.
 *
 * @param {object} conversation
 * @returns {string}
 */
export function getLastMessagePreview(conversation) {
  return (
    conversation?.last_message_preview ||
    conversation?.latest_message_preview ||
    conversation?.last_message_body ||
    conversation?.message_preview ||
    conversation?.subject ||
    conversation?.reference_id ||
    'Open to read the latest message'
  )
}

/**
 * Returns a readable seller-account label.
 *
 * @param {object} conversation
 * @returns {string}
 */
export function sellerAccountLabel(conversation) {
  const sellerAccount = conversation?.seller_account

  return (
    sellerAccount?.account_name ||
    conversation?.provider_account_id ||
    'Unknown account'
  )
}

/**
 * Determines whether an attachment is an image.
 *
 * @param {object} attachment
 * @returns {boolean}
 */
export function isImageAttachment(attachment) {
  const type = String(
    attachment?.media_type ||
    attachment?.mime_type ||
    '',
  ).toLowerCase()

  const url = String(
    attachment?.media_url ||
    attachment?.download_url ||
    '',
  ).toLowerCase()

  return (
    type.includes('image') ||
    /\.(png|jpe?g|gif|webp)(\?|$)/.test(url)
  )
}

/**
 * Determines whether a message is an eBay/provider system notification.
 *
 * @param {object} message
 * @returns {boolean}
 */
export function isEbayNotificationMessage(message) {
  const senderType = String(message?.sender_type || '')
    .trim()
    .toUpperCase()

  return ['EBAY', 'SYSTEM', 'PROVIDER'].includes(senderType)
}

/**
 * Formats an amount using the supplied currency.
 *
 * @param {number|string|null|undefined} amount
 * @param {string} currency
 * @returns {string}
 */
export function formatCurrency(amount, currency = 'USD') {
  if (amount == null) {
    return 'N/A'
  }

  const normalizedCurrency = String(currency || 'USD').toUpperCase()
  const numericAmount = Number(amount)

  if (!Number.isFinite(numericAmount)) {
    return `${amount} ${normalizedCurrency}`
  }

  if (normalizedCurrency === 'AUD') {
    return `AU $${numericAmount.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  }

  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: normalizedCurrency,
    }).format(numericAmount)
  } catch {
    return `${numericAmount} ${normalizedCurrency}`
  }
}

/**
 * Returns the best available timestamp from an offer.
 *
 * @param {object} offer
 * @returns {string|null}
 */
export function offerTimestamp(offer) {
  return (
    offer?.created_at_provider ||
    offer?.createdAtProvider ||
    offer?.created_at ||
    offer?.created_date ||
    offer?.sent_at ||
    offer?.updated_at ||
    null
  )
}

/**
 * Converts a date value into a sortable timestamp.
 *
 * @param {string|Date|null|undefined} value
 * @returns {number}
 */
export function eventTimeValue(value) {
  const time = value ? new Date(value).getTime() : Number.NaN
  return Number.isNaN(time) ? 0 : time
}

/**
 * Returns a readable label for an offer event.
 *
 * @param {object} offer
 * @param {boolean} isSellerOffer
 * @param {string} buyerName
 * @returns {string}
 */
export function getOfferLabel(
  offer,
  isSellerOffer,
  buyerName,
) {
  const status = String(offer?.status || '').toUpperCase()
  const type = String(
    offer?.offer_type ||
    offer?.type ||
    '',
  ).toUpperCase()

  if (status === 'ACCEPTED' || type.includes('ACCEPTED')) {
    return `${buyerName} accepted an offer`
  }

  if (isSellerOffer) {
    return type.includes('COUNTER')
      ? 'You sent a counteroffer'
      : 'You sent an offer'
  }

  if (type.includes('COUNTER')) {
    return `${buyerName} sent a counteroffer`
  }

  return `${buyerName} sent an offer`
}
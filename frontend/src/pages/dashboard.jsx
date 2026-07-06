import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import { fetchCategories } from '../services/categoryApi'
import {
  assignConversation,
  bulkUpdateConversations,
  createConversationNote,
  fetchConversation,
  fetchConversationNotes,
  sendConversationReply,
  sendConversationReplyWithAttachments,
  fetchConversations,
  updateConversationCategory,
  updateConversationStatus,
  translateMessage,
} from '../services/conversationApi'
import { fetchEbayAccounts } from '../services/ebayAccountApi'
import { fetchTemplates } from '../services/templateApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'
import { fetchMessageTypeTree } from '../services/messageTypeApi'
import ReplyComposer from '../components/conversations/ReplyComposer'

const DEFAULT_PAGE_SIZE = 20
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const STATUSES = ['OPEN', 'PENDING', 'RESOLVED', 'CLOSED']
const LIST_WIDTH_KEY = 'inboxListPanelWidth'
const DETAILS_WIDTH_KEY = 'inboxDetailsPanelWidth'
const SHOW_MESSAGE_ATTACHMENTS = true

function getStoredNumber(key, fallback) {
  const value = Number(localStorage.getItem(key))
  return Number.isFinite(value) ? value : fallback
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function formatDate(value) {
  if (!value) {
    return 'Not available'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelativeDeadline(value) {
  if (!value) {
    return 'No deadline'
  }

  const due = new Date(value)
  if (Number.isNaN(due.getTime())) {
    return value
  }

  const diffMs = due.getTime() - Date.now()
  const absHours = Math.abs(diffMs) / 36e5
  if (diffMs < 0) {
    return absHours < 1 ? 'Overdue' : `${Math.ceil(absHours)}h overdue`
  }

  if (absHours < 1) {
    return 'Due soon'
  }

  return `${Math.ceil(absHours)}h left`
}

function deadlineTone(value) {
  if (!value) {
    return 'neutral'
  }

  const diffMs = new Date(value).getTime() - Date.now()
  if (diffMs < 0) {
    return 'danger'
  }
  if (diffMs < 4 * 36e5) {
    return 'warning'
  }
  return 'good'
}

function normalizeUser(user) {
  return {
    id: user.id,
    fullName: user.full_name || user.name || user.fullName || user.email || 'Unknown user',
    email: user.email || '',
    role: user.role || '',
    isActive: user.is_active !== false,
  }
}

function normalizeCategory(category) {
  return {
    id: category.id,
    name: category.name,
    color: category.color || '#2563eb',
    isActive: category.is_active !== false,
  }
}

function normalizeAccount(account) {
  return {
    id: account.id,
    label: account.ebay_username || account.store_name || account.account_name || account.id,
  }
}

function conversationTypeLabel(value) {
  const labels = {
    FROM_MEMBERS: 'From members',
    FROM_EBAY: 'From eBay',
  }
  return labels[value] || value || 'Unknown source'
}

function isEbaySystemConversation(conversation) {
  return conversation?.provider_conversation_type === 'FROM_EBAY'
}

function isHtmlBody(value) {
  return /<\/?[a-z][\s\S]*>/i.test(value || '')
}

function getList(response) {
  if (Array.isArray(response)) {
    return response
  }

  return response.items || response.data || response.users || response.categories || []
}

function getInitials(name) {
  return String(name || 'U')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

function userLabel(user) {
  if (!user) {
    return 'Unassigned'
  }

  return user.full_name || user.name || user.fullName || user.email || 'Unknown user'
}

function getLastMessagePreview(conversation) {
  return (
    conversation.last_message_preview ||
    conversation.latest_message_preview ||
    conversation.last_message_body ||
    conversation.message_preview ||
    conversation.subject ||
    conversation.reference_id ||
    'Open to read the latest message'
  )
}

function sellerAccountLabel(conversation) {
  const sellerAccount = conversation.seller_account
  return (
    sellerAccount?.store_name ||
    sellerAccount?.ebay_username ||
    sellerAccount?.account_name ||
    conversation.provider_account_id ||
    'Unknown account'
  )
}

function ConversationBadge({ children, tone = 'neutral', color }) {
  return (
    <span
      className={`conversation-badge conversation-badge-${tone}`}
      style={color ? { '--badge-color': color } : undefined}
    >
      {children}
    </span>
  )
}

function isImageAttachment(attachment) {
  const type = `${attachment.media_type || attachment.mime_type || ''}`.toLowerCase()
  const url = `${attachment.media_url || attachment.download_url || ''}`.toLowerCase()
  return type.includes('image') || /\.(png|jpe?g|gif|webp)(\?|$)/.test(url)
}

function getVisiblePageItems(currentPage, pageCount) {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => index)
  }

  const pages = new Set([0, pageCount - 1, currentPage])
  if (currentPage > 0) {
    pages.add(currentPage - 1)
  }
  if (currentPage + 1 < pageCount) {
    pages.add(currentPage + 1)
  }
  if (currentPage <= 2) {
    pages.add(1)
    pages.add(2)
    pages.add(3)
  }
  if (currentPage >= pageCount - 3) {
    pages.add(pageCount - 2)
    pages.add(pageCount - 3)
    pages.add(pageCount - 4)
  }

  const sortedPages = Array.from(pages)
    .filter((value) => value >= 0 && value < pageCount)
    .sort((a, b) => a - b)
  const items = []
  sortedPages.forEach((pageNumber, index) => {
    if (index > 0 && pageNumber - sortedPages[index - 1] > 1) {
      items.push(`ellipsis-${pageNumber}`)
    }
    items.push(pageNumber)
  })
  return items
}

function EmptyPanel({ title, message }) {
  return (
    <div className="inbox-empty">
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  )
}

function FilterSelect({ label, value, onChange, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {children}
      </select>
    </label>
  )
}

function ConversationRow({ conversation, isSelected, isBulkSelected, onSelect, onToggleBulk }) {
  const title = conversation.subject || conversation.reference_id || 'Customer message'
  const categoryColor = conversation.category?.color
  const deadline = formatRelativeDeadline(conversation.response_due_at)
  const displayStatus = conversation.calculated_status || conversation.status
  const direction = conversation.last_message_direction || 'System'

  return (
    <div
      className={`conversation-row ${isSelected ? 'active' : ''}`}
      onClick={() => onSelect(conversation.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect(conversation.id)
        }
      }}
      role="button"
      tabIndex={0}
    >
      <span className="ticket-select" onClick={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          checked={isBulkSelected}
          onChange={() => onToggleBulk(conversation.id)}
          aria-label={`Select ${conversation.buyer_identifier || 'conversation'}`}
        />
      </span>
      <span className={`ticket-username ${conversation.is_not_read ? 'ticket-not-read' : ''}`}>
        {conversation.is_not_read ? <span className="unread-dot" aria-label="Not read" /> : null}
        <span className="conversation-avatar">{getInitials(conversation.buyer_identifier)}</span>
        <span>
          <strong>{conversation.buyer_identifier || 'Unknown buyer'}</strong>
          <small>{title}</small>
        </span>
      </span>
      <span className="ticket-seller-account">
        <strong>{sellerAccountLabel(conversation)}</strong>
        <small>{conversation.seller_account?.account_name || 'Seller account'}</small>
      </span>
      <span className="ticket-message">
        <span className="conversation-preview">
          {conversation.is_replied ? (
            <span className="reply-indicator" title="Last message is from seller" aria-label="Replied">
              <Icon name="reply" />
            </span>
          ) : null}
          {getLastMessagePreview(conversation)}
        </span>
        <span className="conversation-tags">
          <ConversationBadge tone={direction.toLowerCase()}>
            Last: {direction}
          </ConversationBadge>
          <ConversationBadge tone="category" color={categoryColor}>
            {conversation.category?.name || 'No category'}
          </ConversationBadge>
          <ConversationBadge>{conversationTypeLabel(conversation.provider_conversation_type)}</ConversationBadge>
          <ConversationBadge tone={displayStatus?.toLowerCase().replace(/\s+/g, '-')}>{displayStatus}</ConversationBadge>
        </span>
      </span>
      <span className="ticket-category">
        <ConversationBadge tone="category" color={categoryColor}>
          {conversation.category?.name || 'No category'}
        </ConversationBadge>
      </span>
      <span className="ticket-count" title="Message count">
        <Icon name="message" />
        {conversation.message_count || 0}
      </span>
      <span className={`ticket-deadline ticket-deadline-${deadlineTone(conversation.response_due_at)}`}>
        <strong>{deadline}</strong>
        <small>Respond by</small>
      </span>
      <time className="ticket-last">{formatDate(conversation.last_message_at || conversation.updated_at)}</time>
    </div>
  )
}

function BulkAssignBar({ selectedCount, selectedUser, users, usersError, error, isSubmitting, onUserChange, onAssign, onClear }) {
  if (!selectedCount) {
    return <div className="bulk-assignment-bar empty" aria-hidden="true" />
  }

  return (
    <form className="bulk-assignment-bar" onSubmit={onAssign}>
      <strong>{selectedCount} selected</strong>
      <select value={selectedUser} onChange={(event) => onUserChange(event.target.value)} disabled={Boolean(usersError)}>
        <option value="">Assign to user</option>
        {users.map((user) => (
          <option value={user.id} key={user.id}>
            {user.fullName}
          </option>
        ))}
      </select>
      <button className="primary-button compact" type="submit" disabled={!selectedUser || isSubmitting || Boolean(usersError)}>
        Assign
      </button>
      <button className="secondary-button compact-action" type="button" onClick={onClear}>
        Clear
      </button>
      {error ? (
        <p className="form-message error management-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}

function InboxPagination({ page, pageCount, pageSize, total, onPageChange, onPageSizeChange }) {
  const pageItems = getVisiblePageItems(page, pageCount)
  const start = total ? page * pageSize + 1 : 0
  const end = Math.min((page + 1) * pageSize, total)

  return (
    <div className="pagination-bar">
      <div className="pagination-summary">
        <strong>
          Showing {start}-{end}
        </strong>
        <span>of {total} conversations</span>
      </div>

      <div className="pagination-controls" aria-label="Conversation pagination">
        <button className="pagination-button" type="button" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
          Previous
        </button>
        <div className="pagination-pages">
          {pageItems.map((item) =>
            typeof item === 'string' ? (
              <span className="pagination-ellipsis" key={item}>
                ...
              </span>
            ) : (
              <button
                className={`pagination-page ${item === page ? 'active' : ''}`}
                type="button"
                aria-current={item === page ? 'page' : undefined}
                onClick={() => onPageChange(item)}
                key={item}
              >
                {item + 1}
              </button>
            ),
          )}
        </div>
        <button
          className="pagination-button"
          type="button"
          disabled={page + 1 >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>

      <label className="pagination-size">
        <span>Rows</span>
        <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
          {PAGE_SIZE_OPTIONS.map((option) => (
            <option value={option} key={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

function FiltersDrawer({
  isOpen,
  filters,
  users,
  categories,
  accounts,
  currentUser,
  onFilterChange,
  onSearchSubmit,
  onReset,
  onClose,
}) {
  const [searchInput, setSearchInput] = useState(filters.search)

  useEffect(() => {
    setSearchInput(filters.search)
  }, [filters.search])

  if (!isOpen) {
    return null
  }

  const isAgent = normalizeRole(currentUser?.role) === 'AGENT'
  const assignmentUsers = isAgent
    ? users.filter((user) => user.id === currentUser?.id)
    : users

  function submitSearch(event) {
    event.preventDefault()
    onSearchSubmit(searchInput)
    onClose()
  }

  function resetFilters() {
    setSearchInput('')
    onReset()
    onClose()
  }

  return (
    <div className="filters-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="filters-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="filters-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <h2 id="filters-title">Filters</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close filters">
            <Icon name="close" />
          </button>
        </div>

        <form className="filters-form" onSubmit={submitSearch}>
          <label className="field">
            <span>Search</span>
            <input
              type="search"
              placeholder="Search buyer, subject, item, or message body"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </label>

          <FilterSelect label="Status" value={filters.status} onChange={(value) => onFilterChange('status', value)}>
            <option value="">All statuses</option>
            {STATUSES.map((status) => (
              <option value={status} key={status}>
                {status}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect label="Provider" value={filters.provider} onChange={(value) => onFilterChange('provider', value)}>
            <option value="">All providers</option>
            <option value="ebay">eBay</option>
          </FilterSelect>

          <FilterSelect
            label="Conversation type"
            value={filters.conversation_type}
            onChange={(value) => onFilterChange('conversation_type', value)}
          >
            <option value="">All conversation types</option>
            <option value="FROM_MEMBERS">From members</option>
            <option value="FROM_EBAY">From eBay</option>
          </FilterSelect>

          <FilterSelect
            label="eBay Account"
            value={filters.ebay_account_id}
            onChange={(value) => onFilterChange('ebay_account_id', value)}
          >
            <option value="">All accounts</option>
            {accounts.map((account) => (
              <option value={account.id} key={account.id}>
                {account.label}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Assigned User"
            value={filters.assigned_user_id}
            onChange={(value) => onFilterChange('assigned_user_id', value)}
          >
            <option value="">Anyone</option>
            {assignmentUsers.map((user) => (
              <option value={user.id} key={user.id}>
                {user.fullName}
              </option>
            ))}
          </FilterSelect>

          <FilterSelect
            label="Category"
            value={filters.category_id}
            onChange={(value) => onFilterChange('category_id', value)}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option value={category.id} key={category.id}>
                {category.name}
              </option>
            ))}
          </FilterSelect>

          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={resetFilters}>
              Reset
            </button>
            <button className="primary-button compact" type="submit">
              Apply
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}

function isEbayNotificationMessage(message) {
  /**
   * Identify provider-generated notices that should not appear as either
   * buyer or seller speech. Provider payloads have used several equivalent
   * sender labels over time, so the check intentionally normalizes them.
   */
  const senderType = String(message.sender_type || '').trim().toUpperCase()
  return ['EBAY', 'SYSTEM', 'PROVIDER'].includes(senderType)
}

function resizeEbayMessageFrame(event) {
  /**
   * Expand an eBay srcDoc frame to its complete document height.
   * The frame does not own scrolling; the surrounding message history remains
   * the single scroll surface for provider notices and ordinary messages.
   */
  const frame = event.currentTarget
  const documentElement = frame.contentDocument?.documentElement
  const body = frame.contentDocument?.body
  if (!documentElement || !body) {
    return
  }
  frame.style.height = `${Math.max(documentElement.scrollHeight, body.scrollHeight, 160)}px`
}


// ============================================
// HELPER FUNCTIONS (defined once at the top)
// ============================================
function formatCurrency(amount, currency = 'USD') {
  if (amount == null) return 'N/A'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD'
    }).format(amount)
  } catch {
    return `${amount} ${currency || 'USD'}`
  }
}

function getOfferLabel(offer, isSellerOffer) {
  const status = String(offer.status || '').toUpperCase()
  const type = String(offer.offer_type || offer.type || '').toUpperCase()

  if (status === 'ACCEPTED' || type.includes('ACCEPTED')) {
    return 'accepted an offer'
  }

  if (isSellerOffer) {
    return 'sent a counteroffer'
  }

  if (type.includes('COUNTER')) {
    return 'sent a counteroffer'
  }

  return 'sent an offer'
}


function parseOfferFromMessage(message, conversation) {
  const body = String(message.body || '').trim()
  if (!body) return null

  const lower = body.toLowerCase()

  const isOfferMessage =
    lower.includes('buyer sent an offer') ||
    lower.includes('you sent a counteroffer') ||
    lower.includes('sent a counteroffer') ||
    lower.includes('accepted an offer') ||
    lower.includes('offer accepted')

  if (!isOfferMessage) return null

  const amountMatch = body.match(/\b(USD|EUR|GBP|AUD|CAD|JPY)?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)/i)

  const amount = amountMatch ? Number(amountMatch[2].replace(/,/g, '')) : null
  const currency = amountMatch?.[1]?.toUpperCase() || 'USD'

  const isOutgoing =
    lower.includes('you sent') ||
    lower.includes('seller') ||
    message.is_inbound === false

  const isAccepted =
    lower.includes('accepted an offer') ||
    lower.includes('offer accepted') ||
    String(message.offer_data?.status || '').toUpperCase() === 'ACCEPTED'

  let offerType = isOutgoing ? 'SELLER_COUNTEROFFER' : 'BUYER_OFFER'
  let status = 'PENDING'

  if (isAccepted) {
    offerType = 'ACCEPTED_OFFER'
    status = 'ACCEPTED'
  }

  return {
    id: `message-offer-${message.id}`,
    source_message_id: message.id,
    buyer_username:
      message.offer_data?.buyer_username ||
      conversation?.buyer_identifier ||
      message.sender_identifier ||
      'Buyer',
    direction: isOutgoing ? 'OUTGOING' : 'INCOMING',
    offer_type: offerType,
    type: isOutgoing ? 'SELLER_OFFER' : 'BUYER_OFFER',
    status,
    offer_amount: amount,
    amount,
    currency,
    message: '',
    created_at: message.sent_at || message.created_date,
    created_date: message.sent_at || message.created_date,
    original_body: body,
  }
}

// ============================================
// OFFER EVENT COMPONENT
// ============================================
function OfferEvent({ offer, conversation }) {
  const direction = String(offer.direction || '').toUpperCase()
  const offerType = String(offer.offer_type || offer.type || '').toUpperCase()
  const status = String(offer.status || '').toUpperCase()

  const isSellerOffer =
    direction === 'OUTGOING' ||
    offerType.includes('SELLER') ||
    offerType.includes('COUNTEROFFER') && direction !== 'INCOMING'

  const isAccepted =
    status === 'ACCEPTED' ||
    offerType.includes('ACCEPTED')

  const senderName = isSellerOffer
    ? 'You'
    : offer.buyer_username || conversation?.buyer_identifier || 'Buyer'

  const label = isAccepted
    ? 'accepted an offer'
    : isSellerOffer
      ? 'sent a counteroffer'
      : offerType.includes('COUNTER')
        ? 'sent a counteroffer'
        : 'sent an offer'

  const amount = formatCurrency(
    offer.offer_amount ?? offer.amount,
    offer.currency || 'USD'
  )

  return (
    <div className={`offer-event ${isSellerOffer ? 'offer-event-outgoing' : 'offer-event-incoming'}`}>
      <article className={`offer-card ${isAccepted ? 'offer-card-accepted' : ''}`}>
        <span className="offer-tag-icon" aria-hidden="true">
          {isAccepted ? '✓' : 'Q'}
        </span>

        <div className="offer-card-copy">
          <div className="offer-card-label">
            <span>
              <strong>{senderName}</strong> {label}
            </span>
          </div>

          <strong className="offer-amount">{amount}</strong>

          {offer.message ? (
            <p className="offer-message-text">{offer.message}</p>
          ) : null}
        </div>
      </article>

      <time className="offer-event-time">
        {formatDate(offer.created_at || offer.created_date)}
      </time>
    </div>
  )
}


// ============================================
// MESSAGE THREAD COMPONENT
// ============================================
function MessageThread({ messages, offers = [], isSystemConversation, conversation }) {
  const threadRef = useRef(null)
  const [translations, setTranslations] = useState({})
  const [translatingId, setTranslatingId] = useState(null)

  const translateBuyerMessage = useCallback(async (message) => {
    setTranslatingId(message.id)
    try {
      const result = await translateMessage(message.body, 'en')
      setTranslations((current) => ({ ...current, [message.id]: { text: result.translated_text } }))
    } catch (error) {
      setTranslations((current) => ({ ...current, [message.id]: { error: error.message } }))
    } finally {
      setTranslatingId(null)
    }
  }, [])

  useLayoutEffect(() => {
    const thread = threadRef.current
    const scrollContainer = thread?.closest('.thread-panel')
    if (scrollContainer) {
      scrollContainer.scrollTop = scrollContainer.scrollHeight
    }
  }, [messages, offers])

  // Filter out offers if the conversation is FROM_EBAY
  const events = useMemo(() => {
    const offerEventsFromMessages = []
    const normalMessageEvents = []

    messages.forEach((message) => {
      const parsedOffer = message.offer_data
        ? {
            ...message.offer_data,
            id: `message-offer-${message.id}`,
            source_message_id: message.id,
            buyer_username:
              message.offer_data.buyer_username ||
              conversation?.buyer_identifier ||
              message.sender_identifier,
            direction:
              message.offer_data.direction ||
              (message.is_inbound ? 'INCOMING' : 'OUTGOING'),
            created_at: message.sent_at || message.created_date,
            created_date: message.sent_at || message.created_date,
          }
        : parseOfferFromMessage(message, conversation)

      if (parsedOffer) {
        offerEventsFromMessages.push({
          type: 'offer',
          timestamp: parsedOffer.created_at || parsedOffer.created_date,
          value: parsedOffer,
        })
        return
      }

      normalMessageEvents.push({
        type: 'message',
        timestamp: message.sent_at || message.created_date,
        value: message,
      })
    })

    const offerEventsFromApi = (offers || []).map((offer) => ({
      type: 'offer',
      timestamp: offer.created_at || offer.created_date,
      value: offer,
    }))

    return [
      ...normalMessageEvents,
      ...offerEventsFromMessages,
      ...offerEventsFromApi,
    ].sort((left, right) => {
      const leftTime = new Date(left.timestamp || 0).getTime() || 0
      const rightTime = new Date(right.timestamp || 0).getTime() || 0
      return leftTime - rightTime
    })
  }, [messages, offers, conversation])

  if (!events.length) {
    return <EmptyPanel title="No messages yet" message="This conversation has no stored message bodies." />
  }

  return (
    <div className="message-thread" ref={threadRef}>
      {events.map((event, index) => {
        if (event.type === 'offer') {
          // Pass the conversation context to OfferEvent
          return <OfferEvent 
            offer={event.value} 
            key={`offer-${event.value.id || index}`}
            conversation={conversation}  // Add this
          />
        }

        // Handle regular messages
        const message = event.value
        const isSystem = isEbayNotificationMessage(message)
        const direction = isSystem ? 'system' : message.is_inbound ? 'inbound' : 'outbound'
        const isSeller = direction === 'outbound'
        
        return (
          <article className={`message-bubble ${direction}`} key={message.id || index}>
            <div className="message-meta">
              <strong>
                {direction === 'system' 
                  ? 'eBay notification' 
                  : isSeller 
                    ? 'You' 
                    : message.sender_identifier || message.sender_type || 'Buyer'
                }
              </strong>
              <time>{formatDate(message.sent_at || message.created_date)}</time>
            </div>

            {isSystemConversation && isHtmlBody(message.body) ? (
              <iframe
                className="ebay-html-message"
                title={`eBay message ${message.id}`}
                srcDoc={message.body}
                sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
                scrolling="no"
                onLoad={resizeEbayMessageFrame}
              />
            ) : (
              <p>{message.body || message.message || message.text || ''}</p>
            )}

            {direction === 'inbound' && message.body && (
              <div className="message-translation">
                <button 
                  className="translation-button" 
                  type="button" 
                  disabled={translatingId === message.id} 
                  onClick={() => translateBuyerMessage(message)}
                >
                  {translatingId === message.id ? 'Translating…' : 'Translate to English'}
                </button>
                {translations[message.id]?.text && (
                  <p className="translated-copy">
                    <strong>English:</strong> {translations[message.id].text}
                  </p>
                )}
                {translations[message.id]?.error && (
                  <small role="alert">{translations[message.id].error}</small>
                )}
              </div>
            )}

            {SHOW_MESSAGE_ATTACHMENTS && message.attachments && message.attachments.length > 0 && (
              <div className="message-attachments">
                {message.attachments.map((attachment) => {
                  const attachmentUrl = attachment.media_url || attachment.download_url
                  const attachmentName = attachment.media_name || attachment.file_name
                  return (
                    <div className="attachment-card" key={attachment.id}>
                      {attachmentUrl && isImageAttachment(attachment) ? (
                        <a className="attachment-preview" href={attachmentUrl} target="_blank" rel="noreferrer">
                          <img src={attachmentUrl} alt={attachmentName} loading="lazy" />
                        </a>
                      ) : null}
                      <div>
                        <strong>📎 {attachmentName}</strong>
                        {attachment.file_size ? <small>{Math.round(attachment.file_size / 1024)} KB</small> : null}
                        {attachmentUrl ? (
                          <span>
                            <a href={attachmentUrl} target="_blank" rel="noreferrer">Open</a>
                            <a href={attachmentUrl} download={attachmentName}>Download</a>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            
            {message.read_status !== undefined && message.read_status !== null && (
              <span className="message-status">
                {message.read_status ? '✓ Read' : '● Unread'}
              </span>
            )}
          </article>
        )
      })}
    </div>
  )
}

function ReplyUnavailableNotice() {
  return (
    <div className="reply-unavailable" role="note">
      <strong>Reply unavailable</strong>
      <p>eBay system conversations are read-only and cannot receive replies from this workspace.</p>
    </div>
  )
}


function AssignmentPanel({ detail, users, usersError, isSubmitting, onAssign }) {
  const currentAssignee = detail.current_assignment?.assignee
  const assignments = detail.assignments || []
  const [selectedUser, setSelectedUser] = useState(detail.current_assignee_id || '')

  useEffect(() => {
    setSelectedUser(detail.current_assignee_id || '')
  }, [detail.current_assignee_id])

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Assignment</h3>
        {currentAssignee ? <ConversationBadge tone="open">{userLabel(currentAssignee)}</ConversationBadge> : null}
      </div>

      <div className="assignment-form">
        <select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} disabled={Boolean(usersError)}>
          <option value="">Select user</option>
          {users.map((user) => (
            <option value={user.id} key={user.id}>
              {user.fullName}
            </option>
          ))}
        </select>
        <button
          className="primary-button compact"
          type="button"
          disabled={!selectedUser || isSubmitting}
          onClick={() => onAssign(selectedUser)}
        >
          {detail.current_assignee_id ? 'Reassign' : 'Assign'}
        </button>
      </div>

      {usersError ? <p className="detail-warning">{usersError}</p> : null}

      <div className="history-list">
        {assignments.length ? (
          assignments.map((assignment) => (
            <div className="history-item" key={assignment.id}>
              <strong>{userLabel(assignment.assignee)}</strong>
              <span>
                Assigned by {userLabel(assignment.assigner)} on {formatDate(assignment.assigned_at)}
              </span>
              {assignment.unassigned_at ? <small>Ended {formatDate(assignment.unassigned_at)}</small> : null}
            </div>
          ))
        ) : (
          <p className="detail-muted">No assignment history yet.</p>
        )}
      </div>
    </section>
  )
}

function CategoryPanel({ detail, categories, isSubmitting, onCategoryChange, onStatusChange }) {
  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Workflow</h3>
        <ConversationBadge tone={detail.status?.toLowerCase()}>{detail.status}</ConversationBadge>
      </div>

      <label className="field compact-field">
        <span>Status</span>
        <select value={detail.status || ''} onChange={(event) => onStatusChange(event.target.value)} disabled={isSubmitting}>
          {STATUSES.map((status) => (
            <option value={status} key={status}>
              {status}
            </option>
          ))}
        </select>
      </label>

      <label className="field compact-field">
        <span>Category</span>
        <select
          value={detail.category_id || ''}
          onChange={(event) => onCategoryChange(event.target.value)}
          disabled={isSubmitting}
        >
          <option value="">No category</option>
          {categories.map((category) => (
            <option value={category.id} key={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
    </section>
  )
}

function NotesPanel({ notes, isLoading, isSubmitting, onAddNote }) {
  const [body, setBody] = useState('')

  async function submitNote(event) {
    event.preventDefault()
    if (!body.trim()) {
      return
    }

    await onAddNote(body.trim())
    setBody('')
  }

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Internal Notes</h3>
        <ConversationBadge>{notes.length}</ConversationBadge>
      </div>

      <form className="note-form" onSubmit={submitNote}>
        <textarea
          rows="3"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="Add an internal note"
        />
        <button className="primary-button compact" type="submit" disabled={isSubmitting || !body.trim()}>
          Add Note
        </button>
      </form>

      {isLoading ? <p className="detail-muted">Loading notes...</p> : null}
      <div className="notes-list">
        {notes.length ? (
          notes.map((note) => (
            <article className="note-item" key={note.id}>
              <p>{note.body}</p>
              <span>
                {userLabel(note.author)} - {formatDate(note.created_at)}
              </span>
            </article>
          ))
        ) : (
          <p className="detail-muted">No internal notes yet.</p>
        )}
      </div>
    </section>
  )
}

function MetadataPanel({ detail, accounts }) {
  const account = accounts.find((item) => item.id === detail.provider_account_id)

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Metadata</h3>
        <ConversationBadge>{detail.provider}</ConversationBadge>
      </div>
      <dl className="metadata-list">
        <div>
          <dt>Buyer</dt>
          <dd>{detail.buyer_identifier || 'Not available'}</dd>
        </div>
        <div>
          <dt>eBay Account</dt>
          <dd>{account?.label || detail.provider_account_id || 'Not available'}</dd>
        </div>
        <div>
          <dt>Conversation ID</dt>
          <dd>{detail.provider_conversation_id}</dd>
        </div>
        <div>
          <dt>Reference</dt>
          <dd>{detail.reference_id || 'Not available'}</dd>
        </div>
        <div>
          <dt>Reference Type</dt>
          <dd>{detail.reference_type || 'Not available'}</dd>
        </div>
        <div>
          <dt>Unread</dt>
          <dd>{detail.unread_count}</dd>
        </div>
      </dl>
    </section>
  )
}

function ContextThumbnail({ imageUrl, title }) {
  const [failed, setFailed] = useState(false)
  const normalizedUrl = typeof imageUrl === 'string'
    ? imageUrl.trim().replace(/^http:\/\//i, 'https://').replace(/&amp;/g, '&')
    : ''

  useEffect(() => setFailed(false), [normalizedUrl])

  if (!normalizedUrl || failed) return <Icon name="package" />

  return (
    <img
      src={normalizedUrl}
      alt={title ? `${title} preview` : 'Item preview'}
      loading="eager"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  )
}

function ContextItemBanner({ context, actionLabel, ariaLabel }) {
  const formattedPrice = context.price == null
    ? null
    : new Intl.NumberFormat(undefined, {
        style: context.currency ? 'currency' : 'decimal',
        currency: context.currency || undefined,
      }).format(context.price)
  return (
    <section className="product-context-banner" aria-label={ariaLabel}>
      <div className="product-context-main">
        <div className="product-context-thumb">
          <ContextThumbnail imageUrl={context?.image_url} title={context?.title} />
        </div>

        <div className="product-context-body">
          {context?.item_url ? (
            <a href={context.item_url} target="_blank" rel="noreferrer">
              <strong>{context.title || 'Unknown Item'}</strong>
            </a>
          ) : (
            <strong>{context.title || 'Unknown Item'}</strong>
          )}
          {formattedPrice ? <span className="product-context-price">{formattedPrice}</span> : null}
          {(context.order_id || context.item_id || context.sku) ? (
            <div className="product-context-identifiers">
              {context.order_id ? <span>Order Number: {context.order_id}</span> : null}
              {context.item_id ? <span>Item ID: {context.item_id}</span> : null}
              {context.sku ? <span>SKU: {context.sku}</span> : null}
            </div>
          ) : null}
        </div>
      </div>
      <div className="product-context-actions">
        {context.item_url ? <a className="secondary-button compact-action" href={context.item_url} target="_blank" rel="noreferrer">Open Item</a> : null}
        {actionLabel && context.item_url ? <a className="primary-button compact-action" href={context.item_url} target="_blank" rel="noreferrer">{actionLabel}</a> : null}
      </div>
    </section>
  )
}

function OrderBanner({ order }) {
  const item = order.line_items?.[0] || {}
  const context = {
    title: item.title || `Order ${order.order_id}`,
    image_url: item.image_url,
    item_url: order.ebay_url,
    price: item.price_value,
    currency: item.price_currency,
    order_id: order.order_id,
    item_id: item.item_id || item.listing_id,
    sku: item.sku,
  }
  return <ContextItemBanner context={context} actionLabel="Open Order" ariaLabel="Order context" />
}

function ProductBanner({ context }) {
  return <ContextItemBanner context={{ ...context, item_id: context.reference_id }} actionLabel={context.buy_now_available ? 'Buy It Now' : null} ariaLabel="Product context" />
}

function ConversationContextBanner({ detail }) {
  const order = detail.order_context?.selected_order
  if (order) return <OrderBanner order={order} />

  const context = detail.product_context
  if (!context) return null
  return <ProductBanner context={context} />
}

function DetailsPanel({
  detail,
  notes,
  users,
  usersError,
  categories,
  accounts,
  notesLoading,
  isSubmitting,
  onAssign,
  onAddNote,
  onCategoryChange,
  onStatusChange,
}) {
  return (
    <aside className="side-detail-panel">
      <AssignmentPanel detail={detail} users={users} usersError={usersError} isSubmitting={isSubmitting} onAssign={onAssign} />
      <CategoryPanel
        detail={detail}
        categories={categories}
        isSubmitting={isSubmitting}
        onCategoryChange={onCategoryChange}
        onStatusChange={onStatusChange}
      />
      <MetadataPanel detail={detail} accounts={accounts} />
      <NotesPanel notes={notes} isLoading={notesLoading} isSubmitting={isSubmitting} onAddNote={onAddNote} />
    </aside>
  )
}

function ConversationDetail({
  detail,
  notes,
  users,
  usersError,
  categories,
  accounts,
  templates = [],
  messageTypes = [],
  isLoading,
  notesLoading,
  actionError,
  isSubmitting,
  isDetailsOpen,
  mobilePane,
  onBack,
  onOpenDetails,
  onHideDetails,
  onCloseDetails,
  onAssign,
  onAddNote,
  onCategoryChange,
  onStatusChange,
  onSendReply,
}) {
  if (isLoading) {
    return <EmptyPanel title="Loading conversation..." message="Fetching the latest conversation detail." />
  }

  if (!detail) {
    return <EmptyPanel title="Select a conversation" message="Choose a conversation from the inbox to inspect it." />
  }

  const isDetailsView = mobilePane === 'details'
  const detailsButtonLabel = isDetailsView ? 'Thread' : isDetailsOpen ? 'Hide Details' : 'Details'
  const detailsButtonAction = isDetailsView ? onCloseDetails : isDetailsOpen ? onHideDetails : onOpenDetails
  const sellerAccount = detail.seller_account

  return (
    <section className="conversation-detail" aria-label="Conversation detail">
      <div className="detail-header">
        <div>
          <button className="thread-back-button" type="button" onClick={onBack}>
          ← Back to inbox
          </button>
        </div>
        <div className="detail-header-actions">
          <ConversationBadge tone={detail.provider_conversation_status === 'ACTIVE' ? 'open' : 'neutral'}>
            {detail.provider_conversation_status || 'Unknown'}
          </ConversationBadge>
          <button className="secondary-button compact-action" type="button" onClick={detailsButtonAction}>
            {detailsButtonLabel}
          </button>
        </div>
      </div>

      {actionError ? (
        <p className="form-message error management-error" role="alert">
          {actionError}
        </p>
      ) : null}

      {isDetailsView ? (
        <DetailsPanel
          detail={detail}
          notes={notes}
          users={users}
          usersError={usersError}
          categories={categories}
          accounts={accounts}
          notesLoading={notesLoading}
          isSubmitting={isSubmitting}
          onAssign={onAssign}
          onAddNote={onAddNote}
          onCategoryChange={onCategoryChange}
          onStatusChange={onStatusChange}
        />
      ) : (
        <div className="thread-panel">
          <ConversationContextBanner detail={detail} />
          <MessageThread 
            messages={detail.messages || []} 
            offers={detail.offers || []} 
            isSystemConversation={isEbaySystemConversation(detail)}
            conversation={detail}  // Pass the conversation
          />        
          {isEbaySystemConversation(detail) ? (
            <ReplyUnavailableNotice />
          ) : (
            <ReplyComposer
              conversationId={detail.id}
              suggestedMessageTypeId={detail.suggested_message_type_id}
              isSubmitting={isSubmitting}
              onSendReply={onSendReply}
              templates={templates}
              messageTypes={messageTypes}
            />
          )}
        </div>
      )}
    </section>
  )
}

function Dashboard({ currentUser, onLogout }) {
  const canManageAssignments = ['ADMIN', 'OPS_MANAGER', 'AGENT'].includes(normalizeRole(currentUser?.role))
  const [filters, setFilters] = useState({
    search: '',
    status: '',
    provider: 'EBAY',
    conversation_type: '',
    ebay_account_id: '',
    assigned_user_id: '',
    category_id: '',
  })
  const [page, setPage] = useState(0)
  const [conversations, setConversations] = useState([])
  const [total, setTotal] = useState(0)
  const [selectedConversationId, setSelectedConversationId] = useState('')
  const [bulkSelectedIds, setBulkSelectedIds] = useState(() => new Set())
  const [bulkAssignedUserId, setBulkAssignedUserId] = useState('')
  const [detail, setDetail] = useState(null)
  const [notes, setNotes] = useState([])
  const [users, setUsers] = useState([])
  const [categories, setCategories] = useState([])
  const [accounts, setAccounts] = useState([])
  const [templates, setTemplates] = useState([])
  const [messageTypes, setMessageTypes] = useState([])
  const [listWidth, setListWidth] = useState(() => getStoredNumber(LIST_WIDTH_KEY, 420))
  const [detailsWidth, setDetailsWidth] = useState(() => getStoredNumber(DETAILS_WIDTH_KEY, 360))
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [isDetailsOpen, setIsDetailsOpen] = useState(true)
  const [isFiltersOpen, setIsFiltersOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState('list')
  const [isListLoading, setIsListLoading] = useState(true)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [isNotesLoading, setIsNotesLoading] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [listError, setListError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [actionError, setActionError] = useState('')
  const [usersError, setUsersError] = useState('')

  const offset = page * pageSize
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const hasSelectedConversation = Boolean(selectedConversationId)

  const workspaceStyle = hasSelectedConversation
    ? {
        gridTemplateColumns: isDetailsOpen
          ? `${listWidth}px 8px minmax(0, 1fr) 8px ${detailsWidth}px`
          : `${listWidth}px 8px minmax(0, 1fr)`,
      }
    : undefined

  // In dashboard.jsx, around line 445
  const loadConversations = useCallback(async () => {
    setIsListLoading(true)
    setListError('')

    try {
      const response = await fetchConversations({
        limit: pageSize,
        offset,
        ...filters,
      })
      console.log('Conversations response:', response) // Add this
      setConversations(response.items || [])
      setTotal(response.total || 0)
    } catch (caughtError) {
      console.error('Error loading conversations:', caughtError) // Add this
      setListError(caughtError.message)
      setConversations([])
      setTotal(0)
    } finally {
      setIsListLoading(false)
    }
  }, [filters, offset, pageSize])

  const loadConversationDetail = useCallback(async (conversationId) => {
    if (!conversationId) {
      setDetail(null)
      setNotes([])
      return
    }

    setIsDetailLoading(true)
    setDetailError('')

    try {
      const response = await fetchConversation(conversationId)
      setDetail(response)
      setConversations((items) => items.map((item) => (item.id === response.id ? { ...item, ...response } : item)))
    } catch (caughtError) {
      console.error('Failed to load conversation detail', { conversationId, error: caughtError })
      setDetailError(caughtError.message || 'Unable to load conversation detail.')
      setDetail(null)
    } finally {
      setIsDetailLoading(false)
    }
  }, [])

  const loadNotes = useCallback(async (conversationId) => {
    if (!conversationId) {
      setNotes([])
      return
    }

    setIsNotesLoading(true)

    try {
      const response = await fetchConversationNotes(conversationId)
      setNotes(getList(response))
    } catch {
      setNotes([])
    } finally {
      setIsNotesLoading(false)
    }
  }, [])

  async function loadSupportData() {
    const [categoryResult, accountResult, userResult, templateResult, messageTypeResult] = await Promise.allSettled([
      fetchCategories(),
      fetchEbayAccounts(),
      fetchUsers(),
      fetchTemplates(),
      fetchMessageTypeTree(),
    ])

    if (categoryResult.status === 'fulfilled') {
      setCategories(getList(categoryResult.value).map(normalizeCategory).filter((category) => category.isActive))
    }

    if (accountResult.status === 'fulfilled') {
      setAccounts(getList(accountResult.value).map(normalizeAccount))
    }

    if (userResult.status === 'fulfilled') {
      setUsers(getList(userResult.value).map(normalizeUser).filter((user) => user.isActive))
      setUsersError('')
    } else {
      setUsersError(userResult.reason?.message || 'Users are unavailable for assignment.')
    }

    if (templateResult.status === 'fulfilled') {
      setTemplates(getList(templateResult.value).filter((template) => template.is_active !== false))
    } else {
      setTemplates([])
    }
    if (messageTypeResult.status === 'fulfilled') setMessageTypes(messageTypeResult.value || [])
  }

  useEffect(() => {
    loadSupportData()
  }, [])

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  useEffect(() => {
    if (page >= pageCount) {
      setPage(pageCount - 1)
    }
  }, [page, pageCount])

  useEffect(() => {
    loadConversationDetail(selectedConversationId)
    loadNotes(selectedConversationId)
  }, [loadConversationDetail, loadNotes, selectedConversationId])

  useEffect(() => {
    localStorage.setItem(LIST_WIDTH_KEY, String(listWidth))
  }, [listWidth])

  useEffect(() => {
    localStorage.setItem(DETAILS_WIDTH_KEY, String(detailsWidth))
  }, [detailsWidth])

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId),
    [conversations, selectedConversationId],
  )

  const bulkSelectedCount = bulkSelectedIds.size
  const activeFilterCount = Object.entries(filters).filter(([key, value]) => key !== 'provider' && Boolean(value)).length

  function beginListResize(event) {
    event.preventDefault()

    function move(mouseEvent) {
      setListWidth(clamp(mouseEvent.clientX - 272, 320, 680))
    }

    function stop() {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', stop)
    }

    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', stop)
  }

  function beginDetailsResize(event) {
    event.preventDefault()

    function move(mouseEvent) {
      setDetailsWidth(clamp(window.innerWidth - mouseEvent.clientX, 300, 560))
    }

    function stop() {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', stop)
    }

    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', stop)
  }

  function selectConversation(conversationId) {
    setSelectedConversationId(conversationId)
    setMobilePane('thread')
  }

  function toggleBulkSelection(conversationId) {
    setBulkSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(conversationId)) {
        next.delete(conversationId)
      } else {
        next.add(conversationId)
      }
      return next
    })
  }

  function clearBulkSelection() {
    setBulkSelectedIds(new Set())
    setBulkAssignedUserId('')
  }

  function returnToList() {
    setSelectedConversationId('')
    setDetail(null)
    setNotes([])
    setMobilePane('list')
  }

  function changePageSize(nextPageSize) {
    setPageSize(nextPageSize)
    setPage(0)
  }

  function changeFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(0)
    setSelectedConversationId('')
    setMobilePane('list')
  }

  function resetFilters() {
    setFilters({
      search: '',
      status: '',
      provider: 'ebay',
      conversation_type: '',
      ebay_account_id: '',
      assigned_user_id: '',
      category_id: '',
    })
    setPage(0)
    setSelectedConversationId('')
    setMobilePane('list')
  }

  async function refreshSelectedConversation() {
    await Promise.all([
      loadConversations(),
      selectedConversationId ? loadConversationDetail(selectedConversationId) : Promise.resolve(),
      selectedConversationId ? loadNotes(selectedConversationId) : Promise.resolve(),
    ])
  }

  async function handleAssign(userId) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await assignConversation(selectedConversationId, userId)
      await refreshSelectedConversation()
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleBulkAssign(event) {
    event.preventDefault()
    const conversationIds = Array.from(bulkSelectedIds)
    if (!conversationIds.length || !bulkAssignedUserId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await bulkUpdateConversations({
        conversation_ids: conversationIds,
        assigned_to: bulkAssignedUserId,
      })
      clearBulkSelection()
      await refreshSelectedConversation()
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleAddNote(body) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      await createConversationNote(selectedConversationId, body)
      await loadNotes(selectedConversationId)
      await loadConversationDetail(selectedConversationId)
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleCategoryChange(categoryId) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      const response = await updateConversationCategory(selectedConversationId, categoryId)
      setDetail(response)
      await loadConversations()
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleStatusChange(status) {
    if (!selectedConversationId) {
      return
    }

    setIsSubmitting(true)
    setActionError('')

    try {
      const response = await updateConversationStatus(selectedConversationId, status)
      setDetail(response)
      await loadConversations()
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSendReply(body, files = [], messageTypeId) {
    if (!selectedConversationId) {
      return
    }
    setIsSubmitting(true)
    setActionError('')
    try {
      const response = files.length
        ? await sendConversationReplyWithAttachments(selectedConversationId, body, files, messageTypeId)
        : await sendConversationReply(selectedConversationId, body, messageTypeId)
      await refreshSelectedConversation()
      if (response.attachment_delivery_warning) {
        setActionError(response.attachment_delivery_warning)
      }
    } catch (caughtError) {
      setActionError(caughtError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AppLayout activePage="Inbox" currentUser={currentUser} onLogout={onLogout}>
      <main
        className={`inbox-page ${hasSelectedConversation ? 'conversation-open' : 'list-only'} ${isDetailsOpen ? '' : 'details-collapsed'}`}
        style={workspaceStyle}
        data-mobile-pane={mobilePane}
      >
        <section className="inbox-list-panel" aria-label="Conversation list">
          <div className="inbox-header">
            <div>
              <span className="inbox-kicker">Live workspace</span>
              <h1>Inbox</h1>
              <p>{total} conversations across your eBay support queue</p>
            </div>
            <div className="inbox-header-actions">
              <button className="secondary-button compact-action" type="button" onClick={() => setIsFiltersOpen(true)}>
                Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}
              </button>
              <button className="icon-button" type="button" onClick={loadConversations} aria-label="Refresh conversations">
                <Icon name="activate" />
              </button>
            </div>
          </div>

          <form
            className="inbox-search-bar"
            onSubmit={(event) => {
              event.preventDefault()
              const formData = new FormData(event.currentTarget)
              changeFilter('search', String(formData.get('search') || '').trim())
            }}
          >
            <input name="search" type="search" placeholder="Search conversations" defaultValue={filters.search} />
            <button className="secondary-button" type="submit">
              Search
            </button>
          </form>

          {canManageAssignments ? (
            <BulkAssignBar
              selectedCount={bulkSelectedCount}
              selectedUser={bulkAssignedUserId}
              users={users}
              usersError={usersError}
              error={actionError}
              isSubmitting={isSubmitting}
              onUserChange={setBulkAssignedUserId}
              onAssign={handleBulkAssign}
              onClear={clearBulkSelection}
            />
          ) : null}

          <div className="conversation-table-head" aria-hidden="true">
            <span></span>
            <span>Username</span>
            <span>Seller Account</span>
            <span>Message</span>
            <span>Category</span>
            <span>Total Chats</span>
            <span>SLA</span>
            <span>Time</span>
          </div>

          {listError ? (
            <p className="form-message error management-error" role="alert">
              {listError}
            </p>
          ) : null}

          <div className="conversation-list">
            {isListLoading ? (
              <EmptyPanel title="Loading conversations..." message="Fetching the latest inbox data." />
            ) : conversations.length ? (
              conversations.map((conversation) => (
                <ConversationRow
                  conversation={conversation}
                  isSelected={conversation.id === selectedConversationId}
                  isBulkSelected={bulkSelectedIds.has(conversation.id)}
                  onSelect={selectConversation}
                  onToggleBulk={canManageAssignments ? toggleBulkSelection : () => {}}
                  key={conversation.id}
                />
              ))
            ) : (
              <EmptyPanel title="No conversations found" message="Adjust filters or sync eBay conversations first." />
            )}
          </div>

          <InboxPagination
            page={page}
            pageCount={pageCount}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={changePageSize}
          />
        </section>

        {hasSelectedConversation ? (
          <>
            <button className="resize-handle" type="button" onMouseDown={beginListResize} aria-label="Resize conversation list" />

            <section className="inbox-detail-panel">
              {detailError ? (
                <EmptyPanel title="Could not load conversation" message={detailError} />
              ) : (
                <ConversationDetail
                  detail={detail || selectedConversation}
                  notes={notes}
                  users={users}
                  usersError={usersError}
                  categories={categories}
                  accounts={accounts}
                  templates={templates}
                  messageTypes={messageTypes}
                  isLoading={isDetailLoading}
                  notesLoading={isNotesLoading}
                  actionError={actionError}
                  isSubmitting={isSubmitting}
                  isDetailsOpen={isDetailsOpen}
                  mobilePane={mobilePane}
                  onBack={returnToList}
                  onOpenDetails={() => {
                    setIsDetailsOpen(true)
                    if (window.innerWidth <= 820) {
                      setMobilePane('details')
                    }
                  }}
                  onHideDetails={() => setIsDetailsOpen(false)}
                  onCloseDetails={() => setMobilePane('thread')}
                  onAssign={handleAssign}
                  onAddNote={handleAddNote}
                  onCategoryChange={handleCategoryChange}
                  onStatusChange={handleStatusChange}
                  onSendReply={handleSendReply}
                />
              )}
            </section>

            {isDetailsOpen ? (
              <>
                <button className="resize-handle" type="button" onMouseDown={beginDetailsResize} aria-label="Resize details panel" />
                <DetailsPanel
                  detail={detail || selectedConversation}
                  notes={notes}
                  users={users}
                  usersError={usersError}
                  categories={categories}
                  accounts={accounts}
                  templates={templates}
                  notesLoading={isNotesLoading}
                  isSubmitting={isSubmitting}
                  onAssign={handleAssign}
                  onAddNote={handleAddNote}
                  onCategoryChange={handleCategoryChange}
                  onStatusChange={handleStatusChange}
                />
              </>
            ) : null}
          </>
        ) : null}

        <FiltersDrawer
          isOpen={isFiltersOpen}
          filters={filters}
          users={users}
          categories={categories}
          accounts={accounts}
          currentUser={currentUser}
          onFilterChange={changeFilter}
          onSearchSubmit={(search) => changeFilter('search', search.trim())}
          onReset={resetFilters}
          onClose={() => setIsFiltersOpen(false)}
        />
      </main>
    </AppLayout>
  )
}

export default Dashboard

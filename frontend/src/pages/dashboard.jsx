import { useCallback, useEffect, useMemo, useState } from 'react'

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
  validateConversationReply,
} from '../services/conversationApi'
import { fetchEbayAccounts } from '../services/ebayAccountApi'
import { fetchTemplates } from '../services/templateApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

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

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return 'Unknown size'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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
            {users.map((user) => (
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

function MessageThread({ messages, isSystemConversation }) {
  if (!messages.length) {
    return <EmptyPanel title="No messages yet" message="This conversation has no stored message bodies." />
  }

  return (
    <div className="message-thread">
      {messages.map((message) => (
        <article className={`message-bubble ${message.is_inbound ? 'inbound' : 'outbound'}`} key={message.id}>
          <div className="message-meta">
            <strong>{message.sender_identifier || message.sender_type}</strong>
            <time>{formatDate(message.sent_at)}</time>
          </div>
          {isSystemConversation && isHtmlBody(message.body) ? (
            <iframe
              className="ebay-html-message"
              title={`eBay message ${message.id}`}
              srcDoc={message.body}
              sandbox="allow-popups allow-popups-to-escape-sandbox"
            />
          ) : (
            <p>{message.body}</p>
          )}
          {SHOW_MESSAGE_ATTACHMENTS && message.attachments?.length ? (
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
                          <a href={attachmentUrl} target="_blank" rel="noreferrer">
                            Open
                          </a>
                          <a href={attachmentUrl} download={attachmentName}>
                            Download
                          </a>
                        </span>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : null}
          <span>{message.read_status ? 'Read' : 'Unread'}</span>
        </article>
      ))}
    </div>
  )
}

function ReplyComposer({ conversationId, isSubmitting, onSendReply, templates }) {
  const [body, setBody] = useState('')
  const [files, setFiles] = useState([])
  const [fileInputKey, setFileInputKey] = useState(0)
  const [violations, setViolations] = useState([])
  const [draftMessage, setDraftMessage] = useState('')
  const [isValidating, setIsValidating] = useState(false)
  const [isDraggingFiles, setIsDraggingFiles] = useState(false)

  function addFiles(selectedFiles) {
    const nextFiles = [...files, ...selectedFiles]
    if (nextFiles.length > 5) {
      setViolations(['eBay allows a maximum of 5 attachments per reply.'])
      setFileInputKey((current) => current + 1)
      return
    }
    setViolations([])
    setDraftMessage('')
    setFiles(nextFiles)
    setFileInputKey((current) => current + 1)
  }

  function updateFiles(event) {
    addFiles(Array.from(event.target.files || []))
  }

  function removeFile(fileIndex) {
    setFiles((current) => current.filter((_, index) => index !== fileIndex))
    setDraftMessage('')
  }

  function handleAttachmentDrag(event) {
    event.preventDefault()
    event.stopPropagation()
    setIsDraggingFiles(true)
  }

  function handleAttachmentDragLeave(event) {
    event.preventDefault()
    event.stopPropagation()
    setIsDraggingFiles(false)
  }

  function handleAttachmentDrop(event) {
    event.preventDefault()
    event.stopPropagation()
    setIsDraggingFiles(false)
    addFiles(Array.from(event.dataTransfer.files || []))
  }

  function saveDraft() {
    setViolations([])
    setDraftMessage('Draft saved locally for this conversation.')
  }

  async function submitReply(event) {
    event.preventDefault()
    const trimmedBody = body.trim()
    if (!trimmedBody || !conversationId) {
      return
    }
    setIsValidating(true)
    setViolations([])
    setDraftMessage('')
    try {
      const validation = await validateConversationReply(conversationId, trimmedBody)
      if (!validation.valid) {
        setViolations(validation.violations || ['Reply violates eBay messaging policy.'])
        return
      }
      await onSendReply(trimmedBody, files)
      setBody('')
      setFiles([])
      setDraftMessage('')
      setFileInputKey((current) => current + 1)
    } catch (caughtError) {
      setViolations([caughtError.message])
    } finally {
      setIsValidating(false)
    }
  }

  return (
    <form className="reply-composer" onSubmit={submitReply}>
      <div className="composer-toolbar">
        {templates.length ? (
          <label className="template-toolbar-control">
            <Icon name="message" />
            <span>Template</span>
            <select
              className="template-picker"
              value=""
              aria-label="Insert reply template"
              onChange={(event) => {
                const template = templates.find((item) => item.id === event.target.value)
                if (template) {
                  setBody((current) => {
                    const separator = current.trim() ? '\n\n' : ''
                    return `${current}${separator}${template.body}`
                  })
                }
              }}
            >
              <option value="">Choose</option>
              {templates.map((template) => (
                <option value={template.id} key={template.id}>
                  {template.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <label className="field composer-editor">
        <span>Reply to buyer</span>
        <textarea
          value={body}
          onChange={(event) => {
            setBody(event.target.value)
            setDraftMessage('')
          }}
          rows="4"
          maxLength={2000}
          placeholder="Write a reply without email, phone, external links, or abusive language"
        />
      </label>

      <div
        className={`attachment-dropzone ${isDraggingFiles ? 'dragging' : ''}`}
        onDragOver={handleAttachmentDrag}
        onDragEnter={handleAttachmentDrag}
        onDragLeave={handleAttachmentDragLeave}
        onDrop={handleAttachmentDrop}
      >
        <input
          id={`reply-attachments-${conversationId}`}
          key={fileInputKey}
          type="file"
          multiple
          onChange={updateFiles}
          accept=".pdf,.txt,.jpg,.jpeg,.png,application/pdf,text/plain,image/jpeg,image/png"
        />
        <label htmlFor={`reply-attachments-${conversationId}`}>
          <Icon name="message" />
          <strong>Add attachments</strong>
          <span>Click to upload or drag and drop files here</span>
        </label>
      </div>

      {files.length ? (
        <div className="reply-attachment-list" aria-label="Selected attachments">
          {files.map((file, index) => (
            <span className="reply-attachment-chip" key={`${file.name}-${file.size}-${index}`}>
              <span>
                <strong>{file.name}</strong>
                <small>{formatFileSize(file.size)}</small>
              </span>
              <button type="button" onClick={() => removeFile(index)} aria-label={`Remove ${file.name}`}>
                x
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {violations.length ? (
        <div className="reply-policy-warning" role="alert">
          {violations.map((violation) => (
            <p key={violation}>{violation}</p>
          ))}
        </div>
      ) : null}
      {draftMessage ? (
        <div className="reply-draft-message" role="status">
          <p>{draftMessage}</p>
        </div>
      ) : null}
      <div className="reply-composer-actions">
        <small>
          {files.length} file{files.length === 1 ? '' : 's'} selected | {body.length}/2000 characters
        </small>
        <button className="secondary-button compact" type="button" onClick={saveDraft} disabled={!body.trim() && !files.length}>
          Save Draft
        </button>
        <button className="primary-button compact" type="submit" disabled={!body.trim() || isSubmitting || isValidating}>
          {isValidating ? 'Checking...' : isSubmitting ? 'Sending...' : 'Send Reply'}
        </button>
      </div>
    </form>
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

function ProductContextBanner({ detail }) {
  const context = detail.product_context

  function copyText(value) {
    if (value && navigator.clipboard) {
      navigator.clipboard.writeText(value)
    }
  }

  return (
    <section className="product-context-banner" aria-label="Product context">
      <a className={`product-context-main ${context?.item_url ? '' : 'is-disabled'}`} href={context?.item_url || undefined} target="_blank" rel="noreferrer">
        <div className="product-context-thumb" aria-hidden="true">
          {context?.image_url ? <img src={context.image_url} alt="" /> : <Icon name="package" />}
        </div>
        <div className="product-context-body">
          <strong>{context?.title || 'Product information is still being enriched.'}</strong>
          <span>Item ID: {context?.reference_id || detail.reference_id || '--'}</span>
          <span>Seller: {context?.seller_username || detail.seller_account?.ebay_username || '--'}</span>
          <span>SKU: {detail?.order_context?.selected_order?.line_items?.[0]?.sku || '--'}</span>
          <span>Order: {detail?.order_context?.selected_order?.order_id || '--'}</span>
        </div>
      </a>
      <div className="product-context-actions">
        <a className="secondary-button compact-action" href={context?.item_url || `https://www.ebay.com/itm/${detail.reference_id || ''}`} target="_blank" rel="noreferrer">
          Open Listing
        </a>
        <button className="secondary-button compact-action" type="button" onClick={() => copyText(context?.reference_id || detail.reference_id)}>
          Copy Item ID
        </button>
        {context?.sku ? (
          <button className="secondary-button compact-action" type="button" onClick={() => copyText(context.sku)}>
            Copy SKU
          </button>
        ) : null}
      </div>
    </section>
  )
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
            Back to inbox
          </button>
          <p>{detail.buyer_identifier || 'Unknown buyer'}</p>
          <h2>{detail.subject || detail.reference_id || 'Customer message'}</h2>
          <dl className="detail-account-summary">
            <div>
              <dt>Seller Account</dt>
              <dd>{sellerAccountLabel(detail)}</dd>
            </div>
            <div>
              <dt>eBay Username</dt>
              <dd>{sellerAccount?.ebay_username || 'Not available'}</dd>
            </div>
            <div>
              <dt>Account Name</dt>
              <dd>{sellerAccount?.account_name || 'Not available'}</dd>
            </div>
          </dl>
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
          <ProductContextBanner detail={detail} />
          <MessageThread messages={detail.messages || []} isSystemConversation={isEbaySystemConversation(detail)} />
          {isEbaySystemConversation(detail) ? (
            <ReplyUnavailableNotice />
          ) : (
            <ReplyComposer
              conversationId={detail.id}
              isSubmitting={isSubmitting}
              onSendReply={onSendReply}
              templates={templates}
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
    provider: 'ebay',
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

  const loadConversations = useCallback(async () => {
    setIsListLoading(true)
    setListError('')

    try {
      const response = await fetchConversations({
        limit: pageSize,
        offset,
        ...filters,
      })
      setConversations(response.items || [])
      setTotal(response.total || 0)
    } catch (caughtError) {
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
    const [categoryResult, accountResult, userResult, templateResult] = await Promise.allSettled([
      fetchCategories(),
      fetchEbayAccounts(),
      fetchUsers(),
      fetchTemplates(),
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

  async function handleSendReply(body, files = []) {
    if (!selectedConversationId) {
      return
    }
    setIsSubmitting(true)
    setActionError('')
    try {
      const response = files.length
        ? await sendConversationReplyWithAttachments(selectedConversationId, body, files)
        : await sendConversationReply(selectedConversationId, body)
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

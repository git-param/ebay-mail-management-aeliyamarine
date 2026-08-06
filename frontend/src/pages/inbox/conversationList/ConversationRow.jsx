import { Icon } from '../../../layouts/app_layout'
import {
  conversationTypeLabel,
  formatDate,
  getInitials,
  getLastMessagePreview,
  sellerAccountLabel,
  slaCaption,
  slaLabel,
  slaTone,
} from '../inboxUtils'

function ConversationBadge({
  children,
  tone = 'neutral',
  color,
}) {
  return (
    <span
      className={`conversation-badge conversation-badge-${tone}`}
      style={color ? { '--badge-color': color } : undefined}
    >
      {children}
    </span>
  )
}

function ConversationRow({
  conversation,
  isSelected,
  isBulkSelected,
  onSelect,
  onToggleBulk,
}) {
  const title =
    conversation.subject ||
    conversation.reference_id ||
    'Customer message'

  const categoryColor = conversation.category?.color

  const displayStatus =
    conversation.calculated_status ||
    conversation.status ||
    'OPEN'

  const direction =
    conversation.last_message_direction ||
    'System'

  const directionTone = String(direction).toLowerCase()

  const statusTone = String(displayStatus)
    .toLowerCase()
    .replace(/\s+/g, '-')

  function openConversation() {
    onSelect(conversation.id)
  }

  function handleKeyDown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }

    event.preventDefault()
    openConversation()
  }

  function stopRowSelection(event) {
    event.stopPropagation()
  }

  function toggleBulkSelection() {
    onToggleBulk(conversation.id)
  }

  return (
    <div
      className={`conversation-row ${isSelected ? 'active' : ''}`}
      onClick={openConversation}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-current={isSelected ? 'true' : undefined}
    >
      <span
        className="ticket-select"
        onClick={stopRowSelection}
        onKeyDown={stopRowSelection}
      >
        <input
          type="checkbox"
          checked={Boolean(isBulkSelected)}
          onChange={toggleBulkSelection}
          aria-label={`Select ${
            conversation.buyer_identifier ||
            'conversation'
          }`}
        />
      </span>

      <span
        className={`ticket-username ${
          conversation.is_not_read
            ? 'ticket-not-read'
            : ''
        }`}
      >
        {conversation.is_not_read ? (
          <span
            className="unread-dot"
            aria-label="Not read"
          />
        ) : null}

        <span className="conversation-avatar">
          {getInitials(conversation.buyer_identifier)}
        </span>

        <span>
          <strong>
            {conversation.buyer_identifier ||
              'Unknown buyer'}
          </strong>

          <small>{title}</small>
        </span>
      </span>

      <span className="ticket-seller-account">
        <center>
          <strong>
            {sellerAccountLabel(conversation)}
          </strong>
        </center>
      </span>

      <span className="ticket-message">
        <span className="conversation-preview">
          {conversation.is_replied ? (
            <span
              className="reply-indicator"
              title="Last message is from seller"
              aria-label="Replied"
            >
              <Icon name="reply" />
            </span>
          ) : null}

          {getLastMessagePreview(conversation)}
        </span>

        <span className="conversation-tags">
          <ConversationBadge tone={directionTone}>
            Last: {direction}
          </ConversationBadge>

          <ConversationBadge
            tone="category"
            color={categoryColor}
          >
            {conversation.category?.name ||
              'No category'}
          </ConversationBadge>

          <ConversationBadge>
            {conversationTypeLabel(
              conversation.provider_conversation_type,
            )}
          </ConversationBadge>

          <ConversationBadge tone={statusTone}>
            {displayStatus}
          </ConversationBadge>
        </span>
      </span>

      <span className="ticket-category">
        <ConversationBadge
          tone="category"
          color={categoryColor}
        >
          {conversation.category?.name ||
            'No category'}
        </ConversationBadge>
      </span>

      <span
        className="ticket-count"
        title="Message count"
      >
        <Icon name="message" />
        {conversation.message_count || 0}
      </span>

      <span
        className={`ticket-deadline ticket-deadline-${slaTone(
          conversation,
        )}`}
      >
        <strong>
          {conversation.sla_response_seconds != null ? (
            <Icon name="activate" />
          ) : null}

          {slaLabel(conversation)}
        </strong>

        <small>{slaCaption(conversation)}</small>
      </span>

      <time className="ticket-last">
        {formatDate(
          conversation.last_message_at ||
            conversation.updated_at,
        )}
      </time>
    </div>
  )
}

export { ConversationBadge }
export default ConversationRow
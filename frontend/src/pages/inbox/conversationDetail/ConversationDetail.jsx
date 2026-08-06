import ReplyComposer from '../../../components/conversations/ReplyComposer'

import { ConversationBadge } from '../conversationList/ConversationRow'
import { EmptyPanel } from '../conversationList/ConversationList'
import { isEbaySystemConversation } from '../inboxUtils'
import ConversationContextBanner from './ConversationContextBanner'
import DetailsPanel from './DetailsPanel'
import MessageThread from './MessageThread'

import './conversationDetail.css'

function ReplyUnavailableNotice() {
  return (
    <section
      className="reply-unavailable"
      role="status"
      aria-label="Reply unavailable"
    >
      <strong>
        Reply unavailable
      </strong>

      <p>
        This conversation contains an eBay system
        notification. Replies can only be sent to
        member conversations.
      </p>
    </section>
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
    return (
      <EmptyPanel
        title="Loading conversation..."
        message="Fetching the latest conversation detail."
      />
    )
  }

  if (!detail) {
    return (
      <EmptyPanel
        title="Select a conversation"
        message="Choose a conversation from the inbox to inspect it."
      />
    )
  }

  const isDetailsView =
    mobilePane === 'details'

  const detailsButtonLabel =
    isDetailsView
      ? 'Thread'
      : isDetailsOpen
        ? 'Hide Details'
        : 'Details'

  const detailsButtonAction =
    isDetailsView
      ? onCloseDetails
      : isDetailsOpen
        ? onHideDetails
        : onOpenDetails

  const isSystemConversation =
    isEbaySystemConversation(detail)

  const providerStatus =
    detail.provider_conversation_status ||
    'Unknown'

  const providerStatusTone =
    detail.provider_conversation_status ===
    'ACTIVE'
      ? 'open'
      : 'neutral'

  return (
    <section
      className="conversation-detail"
      aria-label="Conversation detail"
    >
      <div className="detail-header">
        <div>
          <button
            className="thread-back-button"
            type="button"
            onClick={onBack}
          >
            ← Back to inbox
          </button>
        </div>

        <div className="detail-header-actions">
          <ConversationBadge
            tone={providerStatusTone}
          >
            {providerStatus}
          </ConversationBadge>

          <button
            className="secondary-button compact-action"
            type="button"
            onClick={detailsButtonAction}
          >
            {detailsButtonLabel}
          </button>
        </div>
      </div>

      {actionError ? (
        <p
          className="form-message error management-error"
          role="alert"
        >
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
          <ConversationContextBanner
            detail={detail}
          />

          <MessageThread
            messages={detail.messages || []}
            offers={detail.offers || []}
            isSystemConversation={
              isSystemConversation
            }
            conversation={detail}
          />

          {isSystemConversation ? (
            <ReplyUnavailableNotice />
          ) : (
            <ReplyComposer
              conversationId={detail.id}
              suggestedMessageTypeId={
                detail.suggested_message_type_id
              }
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

export { ReplyUnavailableNotice }
export default ConversationDetail
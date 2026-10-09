import ReplyComposer from './ReplyComposer'
import { Icon } from '../../../layouts/app_layout'
import ConversationWorkflowControls from './ConversationWorkflowControls'

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
  currentUser,
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
  isListPaneOpen,
  mobilePane,
  onBack,
  onToggleListPane,
  onOpenDetails,
  onHideDetails,
  onCloseDetails,
  onAssign,
  onUnassign,
  onAddNote,
  onUpdateNote,
  onDeleteNote,
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
      ? 'Show messages'
      : isDetailsOpen
        ? 'Hide details'
        : 'Show details'

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
        <div className="detail-header-navigation">
          <button
            className="conversation-panel-toggle"
            type="button"
            onClick={onToggleListPane}
            aria-label={isListPaneOpen ? 'Hide conversation list' : 'Show conversation list'}
            title={isListPaneOpen ? 'Hide conversation list' : 'Show conversation list'}
            aria-expanded={isListPaneOpen}
          >
            <Icon name="panelLeft" />
          </button>
          <button
            className="thread-back-button"
            type="button"
            onClick={onBack}
          >
            <Icon name="chevronLeft" /> Back to inbox
          </button>
        </div>

        <div className="detail-header-actions">
          <ConversationWorkflowControls
            detail={detail}
            categories={categories}
            isSubmitting={isSubmitting}
            onStatusChange={onStatusChange}
            onCategoryChange={onCategoryChange}
          />
          <ConversationBadge
            tone={providerStatusTone}
          >
            {providerStatus}
          </ConversationBadge>
          <button
            className="conversation-panel-toggle"
            type="button"
            aria-label={detailsButtonLabel}
            title={detailsButtonLabel}
            aria-expanded={isDetailsOpen || isDetailsView}
            onClick={() => {
              if (!isDetailsView && window.innerWidth <= 820) {
                onOpenDetails()
              } else {
                detailsButtonAction()
              }
            }}
          >
            <Icon name="panelRight" />
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

      {!isDetailsView && <ConversationContextBanner detail={detail} />}

      {isDetailsView ? (
        <DetailsPanel
          currentUser={currentUser}
          detail={detail}
          notes={notes}
          users={users}
          usersError={usersError}
          categories={categories}
          accounts={accounts}
          notesLoading={notesLoading}
          isSubmitting={isSubmitting}
          onAssign={onAssign}
          onUnassign={onUnassign}
          onAddNote={onAddNote}
          onUpdateNote={onUpdateNote}
          onDeleteNote={onDeleteNote}
          onCategoryChange={onCategoryChange}
          onStatusChange={onStatusChange}
        />
      ) : (
        <div className="thread-panel">
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
              currentUser={currentUser}
              buyerName={
                detail.buyer_identifier
              }
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

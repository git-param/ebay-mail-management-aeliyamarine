import { useState } from 'react'

import {
  sendFirstBuyerMessage,
  validateFirstBuyerMessage,
} from '../../../services/newBuyerConversationApi'
import ReplyComposer from './ReplyComposer'
import './newBuyerConversation.css'

export default function NewBuyerConversation({
  accounts,
  currentUser,
  templates,
  messageTypes,
  onCancel,
  onSent,
}) {
  const [accountId, setAccountId] = useState('')
  const [buyerUsername, setBuyerUsername] = useState('')
  const [recipient, setRecipient] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const connectedAccounts = accounts.filter((account) => account.canSendMessages)
  const sendingAccount = connectedAccounts.find((account) => account.id === recipient?.accountId)

  function openComposer(event) {
    event.preventDefault()
    const username = buyerUsername.trim()
    const account = connectedAccounts.find((item) => item.id === accountId)
    if (!account || !username || /\s/.test(username)) {
      setError('Select a connected eBay account and enter a username without spaces.')
      return
    }
    if (username.toLowerCase() === account.ebayUsername.toLowerCase()) {
      setError('The buyer username must differ from the sending account.')
      return
    }
    setError('')
    setRecipient({ accountId, buyerUsername: username })
  }

  async function sendMessage(body, files, messageTypeId, sendCopyToEmail) {
    setIsSubmitting(true)
    setError('')
    try {
      const message = await sendFirstBuyerMessage({
        ...recipient, body, files, messageTypeId, sendCopyToEmail,
      })
      onSent(message.conversation_id)
    } catch (caughtError) {
      setError(caughtError.message)
      throw caughtError
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="conversation-detail new-buyer-conversation" aria-label="New buyer conversation">
      <header className="detail-header">
        <h2>New buyer</h2>
        <button
          className="secondary-button compact-action"
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Back to inbox
        </button>
      </header>
      {error && (
        <p className="form-message error management-error" role="alert">{error}</p>
      )}
      {recipient ? (
        <div className="thread-panel">
          <div className="new-buyer-recipient">
            <div>
              <strong>To: {recipient.buyerUsername}</strong>
              <p>From: {sendingAccount?.label}</p>
            </div>
            <button
              className="secondary-button compact-action"
              type="button"
              onClick={() => setRecipient(null)}
              disabled={isSubmitting}
            >
              Change recipient or account
            </button>
          </div>
          <div className="inbox-empty">
            <h2>Start a conversation</h2>
            <p>Compose your first message below. eBay checks the recipient when you send.</p>
          </div>
          <ReplyComposer
            conversationId={`new-buyer:${recipient.accountId}:${recipient.buyerUsername}`}
            buyerName={recipient.buyerUsername}
            currentUser={currentUser}
            templates={templates}
            messageTypes={messageTypes}
            isSubmitting={isSubmitting}
            onSendReply={sendMessage}
            validateMessage={validateFirstBuyerMessage}
            composerLabel="Message buyer"
          />
        </div>
      ) : (
        <form className="new-buyer-form" onSubmit={openComposer}>
          <p>Enter an eBay username to send a message. The buyer does not need to exist in ACES.</p>
          <label htmlFor="new-buyer-account">Send from eBay account</label>
          <select
            id="new-buyer-account"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
            required
          >
            <option value="">Select an eBay account</option>
            {connectedAccounts.map((account) => (
              <option key={account.id} value={account.id}>{account.label}</option>
            ))}
          </select>
          {!connectedAccounts.length && (
            <p role="status">
              No connected eBay accounts available. Connect an account to send messages.
            </p>
          )}
          <label htmlFor="new-buyer-username">Buyer eBay username</label>
          <input
            id="new-buyer-username"
            value={buyerUsername}
            onChange={(event) => setBuyerUsername(event.target.value)}
            maxLength={255}
            autoComplete="off"
            placeholder="Enter the exact eBay username"
            required
          />
          <button
            className="primary-button"
            type="submit"
            disabled={!accountId || !buyerUsername.trim()}
          >
            Open conversation
          </button>
        </form>
      )}
    </section>
  )
}

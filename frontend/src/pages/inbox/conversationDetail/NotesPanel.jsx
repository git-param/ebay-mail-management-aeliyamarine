import { useState } from 'react'

import { ConversationBadge } from '../conversationList/ConversationRow'
import {
  formatDate,
  userLabel,
} from '../inboxUtils'

function NotesPanel({
  notes = [],
  isLoading,
  isSubmitting,
  onAddNote,
}) {
  const [body, setBody] = useState('')

  async function submitNote(event) {
    event.preventDefault()

    const trimmedBody = body.trim()

    if (!trimmedBody || isSubmitting) {
      return
    }

    await onAddNote(trimmedBody)
    setBody('')
  }

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Internal Notes</h3>

        <ConversationBadge>
          {notes.length}
        </ConversationBadge>
      </div>

      <form
        className="note-form"
        onSubmit={submitNote}
      >
        <textarea
          rows="3"
          value={body}
          onChange={(event) =>
            setBody(event.target.value)
          }
          placeholder="Add an internal note"
          disabled={isSubmitting}
        />

        <button
          className="primary-button compact"
          type="submit"
          disabled={
            isSubmitting ||
            !body.trim()
          }
        >
          {isSubmitting
            ? 'Adding...'
            : 'Add Note'}
        </button>
      </form>

      {isLoading ? (
        <p className="detail-muted">
          Loading notes...
        </p>
      ) : null}

      {!isLoading ? (
        <div className="notes-list">
          {notes.length ? (
            notes.map((note) => (
              <article
                className="note-item"
                key={note.id}
              >
                <p>{note.body}</p>

                <span>
                  {userLabel(note.author)}
                  {' - '}
                  {formatDate(
                    note.created_at,
                  )}
                </span>
              </article>
            ))
          ) : (
            <p className="detail-muted">
              No internal notes yet.
            </p>
          )}
        </div>
      ) : null}
    </section>
  )
}

export default NotesPanel
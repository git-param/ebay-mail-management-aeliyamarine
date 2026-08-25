import { useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
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
  onUpdateNote,
  onDeleteNote,
}) {
  const [body, setBody] = useState('')
  const [editingNoteId, setEditingNoteId] = useState('')
  const [editBody, setEditBody] = useState('')
  const [noteToDelete, setNoteToDelete] = useState(null)

  async function submitNote(event) {
    event.preventDefault()

    const trimmedBody = body.trim()

    if (!trimmedBody || isSubmitting) {
      return
    }

    await onAddNote(trimmedBody)
    setBody('')
  }

  function beginEdit(note) {
    setEditingNoteId(note.id)
    setEditBody(note.body)
  }

  function cancelEdit() {
    setEditingNoteId('')
    setEditBody('')
  }

  async function submitEdit(event, note) {
    event.preventDefault()
    const trimmedBody = editBody.trim()

    if (!trimmedBody || isSubmitting) {
      return
    }

    await onUpdateNote(note.id, trimmedBody)
    cancelEdit()
  }

  async function confirmDelete() {
    if (!noteToDelete || isSubmitting) {
      return
    }

    await onDeleteNote(noteToDelete.id)
    setNoteToDelete(null)
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
            notes.map((note) => {
              const isEditing =
                editingNoteId === note.id
              const isEdited =
                note.updated_at &&
                note.created_at &&
                note.updated_at !==
                  note.created_at

              return (
              <article
                className="note-item"
                key={note.id}
              >
                {isEditing ? (
                  <form
                    className="note-edit-form"
                    onSubmit={(event) =>
                      submitEdit(event, note)
                    }
                  >
                    <textarea
                      rows="3"
                      value={editBody}
                      onChange={(event) =>
                        setEditBody(
                          event.target.value,
                        )
                      }
                      disabled={isSubmitting}
                    />

                    <div className="note-actions">
                      <button
                        className="secondary-button compact-action"
                        type="button"
                        onClick={cancelEdit}
                        disabled={isSubmitting}
                      >
                        Cancel
                      </button>

                      <button
                        className="primary-button compact-action"
                        type="submit"
                        disabled={
                          isSubmitting ||
                          !editBody.trim()
                        }
                      >
                        {isSubmitting
                          ? 'Saving...'
                          : 'Save'}
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div className="note-item-header">
                      <p>{note.body}</p>

                      <div className="note-actions">
                        <button
                          className="icon-button"
                          type="button"
                          title="Edit note"
                          aria-label="Edit note"
                          onClick={() =>
                            beginEdit(note)
                          }
                          disabled={isSubmitting}
                        >
                          <Icon name="edit" />
                        </button>

                        <button
                          className="icon-button note-delete-button"
                          type="button"
                          title="Delete note"
                          aria-label="Delete note"
                          onClick={() =>
                            setNoteToDelete(note)
                          }
                          disabled={isSubmitting}
                        >
                          <Icon name="trash" />
                        </button>
                      </div>
                    </div>

                    <span>
                      {userLabel(note.author)}
                      {' - '}
                      {formatDate(
                        note.created_at,
                      )}
                      {isEdited
                        ? ' - Edited'
                        : ''}
                    </span>
                  </>
                )}
              </article>
              )
            })
          ) : (
            <p className="detail-muted">
              No internal notes yet.
            </p>
          )}
        </div>
      ) : null}

      {noteToDelete ? (
        <div className="modal-backdrop" role="presentation">
          <section
            className="modal-panel note-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-note-title"
          >
            <div className="modal-header">
              <h2 id="delete-note-title">
                Delete internal note?
              </h2>

              <button
                className="icon-button"
                type="button"
                onClick={() => setNoteToDelete(null)}
                aria-label="Close"
                disabled={isSubmitting}
              >
                <Icon name="close" />
              </button>
            </div>

            <p className="confirm-message">
              This internal note will be removed. Are you sure you want to delete it?
            </p>

            <div className="modal-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setNoteToDelete(null)}
                disabled={isSubmitting}
              >
                Cancel
              </button>

              <button
                className="danger-button"
                type="button"
                onClick={confirmDelete}
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? 'Deleting...'
                  : 'Delete'}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  )
}

export default NotesPanel

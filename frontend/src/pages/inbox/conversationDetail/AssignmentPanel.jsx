import { useEffect, useState } from 'react'

import { ConversationBadge } from '../conversationList/ConversationRow'
import {
  formatDate,
  userLabel,
} from '../inboxUtils'

function AssignmentPanel({
  detail,
  users,
  usersError,
  isSubmitting,
  onAssign,
}) {
  const currentAssignee =
    detail.current_assignment?.assignee

  const assignments =
    detail.assignments || []

  const [selectedUser, setSelectedUser] =
    useState(
      detail.current_assignee_id || '',
    )

  useEffect(() => {
    setSelectedUser(
      detail.current_assignee_id || '',
    )
  }, [detail.current_assignee_id])

  function assignSelectedUser() {
    if (!selectedUser) {
      return
    }

    onAssign(selectedUser)
  }

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Assignment</h3>

        {currentAssignee ? (
          <ConversationBadge tone="open">
            {userLabel(currentAssignee)}
          </ConversationBadge>
        ) : null}
      </div>

      <div className="assignment-form">
        <select
          value={selectedUser}
          onChange={(event) =>
            setSelectedUser(
              event.target.value,
            )
          }
          disabled={
            Boolean(usersError) ||
            isSubmitting
          }
          aria-label="Conversation assignee"
        >
          <option value="">
            Select user
          </option>

          {users.map((user) => (
            <option
              value={user.id}
              key={user.id}
            >
              {user.fullName}
            </option>
          ))}
        </select>

        <button
          className="primary-button compact"
          type="button"
          disabled={
            !selectedUser ||
            isSubmitting ||
            Boolean(usersError)
          }
          onClick={assignSelectedUser}
        >
          {isSubmitting
            ? 'Saving...'
            : detail.current_assignee_id
              ? 'Reassign'
              : 'Assign'}
        </button>
      </div>

      {usersError ? (
        <p
          className="detail-warning"
          role="alert"
        >
          {usersError}
        </p>
      ) : null}

      <div className="history-list">
        {assignments.length ? (
          assignments.map(
            (assignment) => (
              <div
                className="history-item"
                key={assignment.id}
              >
                <strong>
                  {userLabel(
                    assignment.assignee,
                  )}
                </strong>

                <span>
                  Assigned by{' '}
                  {userLabel(
                    assignment.assigner,
                  )}{' '}
                  on{' '}
                  {formatDate(
                    assignment.assigned_at,
                  )}
                </span>

                {assignment.unassigned_at ? (
                  <small>
                    Ended{' '}
                    {formatDate(
                      assignment.unassigned_at,
                    )}
                  </small>
                ) : null}
              </div>
            ),
          )
        ) : (
          <p className="detail-muted">
            No assignment history yet.
          </p>
        )}
      </div>
    </section>
  )
}

export default AssignmentPanel
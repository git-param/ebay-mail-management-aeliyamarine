function BulkAssignBar({
  selectedCount,
  selectedUser,
  users,
  usersError,
  error,
  isSubmitting,
  onUserChange,
  onAssign,
  onClear,
}) {
  if (!selectedCount) {
    return (
      <div
        className="bulk-assignment-bar empty"
        aria-hidden="true"
      />
    )
  }

  return (
    <form
      className="bulk-assignment-bar"
      onSubmit={onAssign}
    >
      <strong>
        {selectedCount} selected
      </strong>

      <select
        value={selectedUser}
        onChange={(event) =>
          onUserChange(event.target.value)
        }
        disabled={Boolean(usersError)}
        aria-label="Assign selected conversations to user"
      >
        <option value="">
          Assign to user
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
        type="submit"
        disabled={
          !selectedUser ||
          isSubmitting ||
          Boolean(usersError)
        }
      >
        {isSubmitting ? 'Assigning...' : 'Assign'}
      </button>

      <button
        className="secondary-button compact-action"
        type="button"
        onClick={onClear}
        disabled={isSubmitting}
      >
        Clear
      </button>

      {usersError ? (
        <p
          className="form-message error management-error"
          role="alert"
        >
          {usersError}
        </p>
      ) : null}

      {error ? (
        <p
          className="form-message error management-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </form>
  )
}

export default BulkAssignBar
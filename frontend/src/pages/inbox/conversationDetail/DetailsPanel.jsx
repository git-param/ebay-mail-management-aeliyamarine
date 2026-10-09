import AssignmentPanel from './AssignmentPanel'
import MetadataPanel from './MetadataPanel'
import NotesPanel from './NotesPanel'
import AdditionalDetailsPanel from './AdditionalDetailsPanel'

function DetailsPanel({
  currentUser,
  detail,
  notes,
  users,
  usersError,
  accounts,
  notesLoading,
  isSubmitting,
  onAssign,
  onUnassign,
  onAddNote,
  onUpdateNote,
  onDeleteNote,
}) {
  return (
    <aside
      className="side-detail-panel"
      aria-label="Conversation details"
    >
      <AssignmentPanel
        currentUser={currentUser}
        detail={detail}
        users={users}
        usersError={usersError}
        isSubmitting={isSubmitting}
        onAssign={onAssign}
        onUnassign={onUnassign}
      />

      <MetadataPanel
        detail={detail}
        accounts={accounts}
      />

      <AdditionalDetailsPanel key={detail.id} conversationId={detail.id} />

      <NotesPanel
        notes={notes}
        isLoading={notesLoading}
        isSubmitting={isSubmitting}
        onAddNote={onAddNote}
        onUpdateNote={onUpdateNote}
        onDeleteNote={onDeleteNote}
      />
    </aside>
  )
}

export default DetailsPanel

import AssignmentPanel from './AssignmentPanel'
import CategoryPanel from './CategoryPanel'
import MetadataPanel from './MetadataPanel'
import NotesPanel from './NotesPanel'

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
  onUpdateNote,
  onDeleteNote,
  onCategoryChange,
  onStatusChange,
}) {
  return (
    <aside
      className="side-detail-panel"
      aria-label="Conversation details"
    >
      <AssignmentPanel
        detail={detail}
        users={users}
        usersError={usersError}
        isSubmitting={isSubmitting}
        onAssign={onAssign}
      />

      <CategoryPanel
        detail={detail}
        categories={categories}
        isSubmitting={isSubmitting}
        onCategoryChange={onCategoryChange}
        onStatusChange={onStatusChange}
      />

      <MetadataPanel
        detail={detail}
        accounts={accounts}
      />

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

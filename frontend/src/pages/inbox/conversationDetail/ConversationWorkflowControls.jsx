import { STATUSES } from '../inboxUtils'

export default function ConversationWorkflowControls({
  detail,
  categories = [],
  isSubmitting,
  onStatusChange,
  onCategoryChange,
}) {
  return (
    <div className="conversation-workflow-controls">
      <label>
        <span>Status</span>
        <select
          value={detail.status || 'OPEN'}
          disabled={isSubmitting}
          onChange={(event) => onStatusChange(event.target.value)}
        >
          {STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
        </select>
      </label>
      <label>
        <span>Category</span>
        <select
          value={detail.category_id || ''}
          disabled={isSubmitting}
          onChange={(event) => onCategoryChange(event.target.value)}
        >
          <option value="">No category</option>
          {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
      </label>
    </div>
  )
}

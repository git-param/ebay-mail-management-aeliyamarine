import { ConversationBadge } from '../conversationList/ConversationRow'
import { STATUSES } from '../inboxUtils'

function CategoryPanel({
  detail,
  categories,
  isSubmitting,
  onCategoryChange,
  onStatusChange,
}) {
  const status =
    detail.status || 'OPEN'

  const statusTone = String(status)
    .toLowerCase()
    .replace(/\s+/g, '-')

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Workflow</h3>

        <ConversationBadge
          tone={statusTone}
        >
          {status}
        </ConversationBadge>
      </div>

      <label className="field compact-field">
        <span>Status</span>

        <select
          value={status}
          onChange={(event) =>
            onStatusChange(
              event.target.value,
            )
          }
          disabled={isSubmitting}
        >
          {STATUSES.map(
            (statusOption) => (
              <option
                value={statusOption}
                key={statusOption}
              >
                {statusOption}
              </option>
            ),
          )}
        </select>
      </label>

      <label className="field compact-field">
        <span>Category</span>

        <select
          value={detail.category_id || ''}
          onChange={(event) =>
            onCategoryChange(
              event.target.value,
            )
          }
          disabled={isSubmitting}
        >
          <option value="">
            No category
          </option>

          {categories.map(
            (category) => (
              <option
                value={category.id}
                key={category.id}
              >
                {category.name}
              </option>
            ),
          )}
        </select>
      </label>
    </section>
  )
}

export default CategoryPanel
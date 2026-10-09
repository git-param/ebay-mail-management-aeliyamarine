import { useEffect } from 'react'
import { Icon } from '../../../layouts/app_layout'

/**
 * Message Type controls used by the reply composer.
 *
 * The API returns one suggested ID when a conversation is opened. This
 * component translates that ID into the existing parent/subtype dropdowns.
 * Both selects stay controlled by ReplyComposer, so agents can always replace
 * the automatic suggestion before sending a reply.
 */
export default function MessageTypeSelector({
  conversationId,
  suggestedMessageTypeId,
  messageTypes,
  categoryId,
  subtypeId,
  showRequiredError,
  onCategoryChange,
  onSubtypeChange,
}) {
  const category = messageTypes.find((item) => item.id === categoryId)
  const categoryIsMissing = showRequiredError && !categoryId
  const subtypeIsMissing = showRequiredError && Boolean(category?.children?.length) && !subtypeId

  useEffect(() => {
    onCategoryChange('')
    onSubtypeChange('')
    if (!suggestedMessageTypeId) return

    const root = messageTypes.find((item) => item.id === suggestedMessageTypeId)
    if (root) {
      onCategoryChange(root.id)
      return
    }

    const parent = messageTypes.find((item) =>
      item.children?.some((child) => child.id === suggestedMessageTypeId),
    )
    if (parent) {
      onCategoryChange(parent.id)
      onSubtypeChange(suggestedMessageTypeId)
    }
  }, [conversationId, suggestedMessageTypeId, messageTypes, onCategoryChange, onSubtypeChange])

  return (
    <>
      <label className={`composer-select-control${categoryIsMissing ? ' has-error' : ''}`}>
        <span>Message Type *</span>
        <Icon name="tag" />
        <select
          value={categoryId}
          aria-invalid={categoryIsMissing}
          onChange={(event) => {
            onCategoryChange(event.target.value)
            onSubtypeChange('')
          }}
        >
          <option value="">Message type *</option>
          {messageTypes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
      </label>
      {category?.children?.length ? (
        <label className={`composer-select-control${subtypeIsMissing ? ' has-error' : ''}`}>
          <span>Sub Type *</span>
          <Icon name="tag" />
          <select
            value={subtypeId}
            aria-invalid={subtypeIsMissing}
            onChange={(event) => onSubtypeChange(event.target.value)}
          >
            <option value="">Message subtype *</option>
            {category.children.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
        </label>
      ) : null}
    </>
  )
}

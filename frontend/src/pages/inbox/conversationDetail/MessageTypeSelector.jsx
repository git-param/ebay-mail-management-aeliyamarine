import { useEffect } from 'react'

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
  onCategoryChange,
  onSubtypeChange,
}) {
  const category = messageTypes.find((item) => item.id === categoryId)

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
      <label className="composer-select-control">
        <span>Message Type *</span>
        <select
          value={categoryId}
          onChange={(event) => {
            onCategoryChange(event.target.value)
            onSubtypeChange('')
          }}
        >
          <option value="">Select type</option>
          {messageTypes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
      </label>
      {category?.children?.length ? (
        <label className="composer-select-control">
          <span>Sub Type *</span>
          <select value={subtypeId} onChange={(event) => onSubtypeChange(event.target.value)}>
            <option value="">Select subtype</option>
            {category.children.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
        </label>
      ) : null}
    </>
  )
}

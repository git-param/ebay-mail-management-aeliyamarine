import { ConversationBadge } from '../conversationList/ConversationRow'
import { formatDate } from '../inboxUtils'

function MetadataValue({
  children,
  fallback = 'Not available',
}) {
  const hasValue =
    children !== null &&
    children !== undefined &&
    children !== ''

  return hasValue
    ? children
    : fallback
}

function MetadataPanel({
  detail,
  accounts = [],
}) {
  const account = accounts.find(
    (item) =>
      item.id ===
      detail.provider_account_id,
  )

  const provider =
    detail.provider ||
    'EBAY'

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Metadata</h3>

        <ConversationBadge>
          {provider}
        </ConversationBadge>
      </div>

      <dl className="metadata-list">
        <div>
          <dt>Buyer</dt>

          <dd>
            <MetadataValue>
              {detail.buyer_identifier}
            </MetadataValue>
          </dd>
        </div>

        <div>
          <dt>eBay Account</dt>

          <dd>
            <MetadataValue>
              {account?.label ||
                detail.provider_account_id}
            </MetadataValue>
          </dd>
        </div>

        <div>
          <dt>Conversation ID</dt>

          <dd>
            <MetadataValue>
              {detail.provider_conversation_id}
            </MetadataValue>
          </dd>
        </div>

        <div>
          <dt>Reference</dt>

          <dd>
            <MetadataValue>
              {detail.reference_id}
            </MetadataValue>
          </dd>
        </div>

        <div>
          <dt>Reference Type</dt>

          <dd>
            <MetadataValue>
              {detail.reference_type}
            </MetadataValue>
          </dd>
        </div>

        <div>
          <dt>Unread</dt>

          <dd>
            {detail.is_not_read
              ? 'Yes'
              : 'No'}
          </dd>
        </div>

        <div>
          <dt>Created</dt>

          <dd>
            {formatDate(
              detail.created_at,
            )}
          </dd>
        </div>

        <div>
          <dt>Last Updated</dt>

          <dd>
            {formatDate(
              detail.updated_at,
            )}
          </dd>
        </div>

        <div>
          <dt>Last Message</dt>

          <dd>
            {formatDate(
              detail.last_message_at,
            )}
          </dd>
        </div>
      </dl>
    </section>
  )
}

export { MetadataValue }
export default MetadataPanel
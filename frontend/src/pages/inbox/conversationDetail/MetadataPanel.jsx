import { Icon } from '../../../layouts/app_layout'
import { ConversationBadge } from '../conversationList/ConversationRow'
import ConversationProductCard from './ConversationProductCard'
import { conversationProductContext, metadataText } from './conversationProductContext'

function MetadataRow({ label, value, url, linkLabel }) {
  const text = metadataText(value)
  if (!text) return null
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        <span>{text}</span>
        {url ? (
          <a className="metadata-external-link" href={url} target="_blank"
            rel="noopener noreferrer" title={linkLabel} aria-label={linkLabel}>
            <Icon name="external" />
          </a>
        ) : null}
      </dd>
    </div>
  )
}

export default function MetadataPanel({ detail, accounts = [] }) {
  const account = accounts.find((item) => item.id === detail.provider_account_id)
  const context = conversationProductContext(detail)

  return (
    <section className="detail-section">
      <div className="section-heading">
        <h3>Metadata</h3>
        <ConversationBadge>{detail.provider || 'EBAY'}</ConversationBadge>
      </div>
      <ConversationProductCard context={context} />
      <dl className="metadata-list">
        <MetadataRow label="Buyer" value={detail.buyer_identifier} />
        <MetadataRow label="eBay Account"
          value={metadataText(account?.label) || detail.provider_account_id} />
        <MetadataRow label="Item Number" value={context.itemNumber}
          url={context.itemUrl} linkLabel="Open item" />
        <MetadataRow label="Reference" value={context.reference} />
        {context.reference ? <MetadataRow label="Reference Type" value={context.referenceType} /> : null}
        <MetadataRow label="Order Number" value={context.orderNumber}
          url={context.orderUrl} linkLabel="Open order" />
        <MetadataRow label="SKU" value={context.sku} />
      </dl>
    </section>
  )
}

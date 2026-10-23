import { useState } from 'react'

import { Icon } from '../../../layouts/app_layout'
import { ConversationBadge } from '../conversationList/ConversationRow'
import ConversationProductCard from './ConversationProductCard'
import { conversationProductContext, metadataText } from './conversationProductContext'

async function copyLink(url) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url)
      return
    } catch {
      // Use the selection fallback when clipboard access is blocked.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = url
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    if (!document.execCommand('copy')) throw new Error('Clipboard copy failed')
  } finally {
    textarea.remove()
  }
}

function MetadataRow({ label, value, url, linkLabel, copyLabel }) {
  const [copyResult, setCopyResult] = useState(null)
  const text = metadataText(value)
  if (!text) return null
  const copyStatus = copyResult && copyResult.url === url ? copyResult.message : ''

  async function copyUrl() {
    try {
      await copyLink(url)
      setCopyResult({ url, message: 'Copied' })
    } catch {
      setCopyResult({ url, message: 'Could not copy' })
    }
  }

  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {url ? (
          <button className="metadata-value-copy" type="button"
            onClick={copyUrl} title={copyLabel} aria-label={copyLabel}>
            {text}
          </button>
        ) : <span>{text}</span>}
        {url ? <span className="metadata-copy-status" role="status">{copyStatus}</span> : null}
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
          url={context.itemUrl} linkLabel="Open item" copyLabel="Copy item link" />
        <MetadataRow label="Reference" value={context.reference} />
        {context.reference ? <MetadataRow label="Reference Type" value={context.referenceType} /> : null}
        <MetadataRow label="Order Number" value={context.orderNumber}
          url={context.orderUrl} linkLabel="Open order" copyLabel="Copy order link" />
        <MetadataRow label="SKU" value={context.sku} />
      </dl>
    </section>
  )
}

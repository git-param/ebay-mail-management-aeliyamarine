import { useState } from 'react'
import { Icon } from '../../../layouts/app_layout'
import { normalizeProductImageUrl } from '../../../utils/ebayUrls'

export default function ConversationProductCard({ context }) {
  const [failedUrl, setFailedUrl] = useState('')
  const imageUrl = normalizeProductImageUrl(context.imageUrl)
  if (!context.title && !context.price && !imageUrl) return null

  return (
    <div className="metadata-product-card">
      <div className="metadata-product-thumbnail">
        {imageUrl && failedUrl !== imageUrl ? (
          <img
            src={imageUrl}
            alt={context.title ? `${context.title} preview` : 'Item preview'}
            referrerPolicy="no-referrer"
            onError={() => setFailedUrl(imageUrl)}
          />
        ) : <Icon name="package" />}
      </div>
      <div className="metadata-product-body">
        {context.title ? <strong className="metadata-product-title">{context.title}</strong> : null}
        {context.price ? <span className="metadata-product-price">{context.price}</span> : null}
      </div>
    </div>
  )
}

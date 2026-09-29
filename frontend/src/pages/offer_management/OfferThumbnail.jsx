import { useState } from 'react'
import { normalizeProductImageUrl } from '../../utils/ebayUrls'

export default function OfferThumbnail({ listing, href }) {
  const [failedUrls, setFailedUrls] = useState([])
  const candidates = [...new Set([listing.image_url, ...(listing.image_urls || [])].map(normalizeProductImageUrl).filter(Boolean))]
  const imageUrl = candidates.find(url => !failedUrls.includes(url))
  const content = imageUrl
    ? <img src={imageUrl} alt={listing.title || 'Product preview'} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailedUrls(current => [...current, imageUrl])} />
    : <span className="bo-image-placeholder"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 5-5 4 4 4-6 5 7" /></svg><span>Preview unavailable</span></span>
  return href ? <a className="best-offer-image" href={href} target="_blank" rel="noreferrer" aria-label={`View ${listing.title || 'item'} on eBay`}>{content}</a> : <div className="best-offer-image">{content}</div>
}

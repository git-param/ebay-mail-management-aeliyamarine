import { bestOfferPrices, bestOfferDate, bestOfferStatusKey, bestOfferStatusLabel, bestOfferStatusGroup, bestOfferGroupLabels } from './bestOfferFormat'

export default function BestOfferCard({ offer, now, onAction, loading }) {
  const listing = offer.listing || {}
  const remaining = offer.expires_at ? Math.max(0, new Date(offer.expires_at).getTime() - now) : null
  const status = bestOfferStatusKey(offer.provider_status || offer.status || offer.display_status)
  const group = offer.status_group || bestOfferStatusGroup(status)
  const prices = bestOfferPrices(offer)
  const closed = ['COMPLETED', 'CLOSED'].includes(group)
  const roleLabel = offer.provider_role === 'Seller' ? 'Your account is selling' : offer.provider_role === 'Buyer' ? 'Your account is buying' : 'Historical record - account role unavailable'
  const countdown = closed ? (group === 'COMPLETED' ? (offer.status_verified && offer.provider_status ? 'Accepted · payment completed' : 'Accepted offer · closed') : 'Offer closed') : group === 'AGREED' ? bestOfferStatusLabel(status) : group === 'UNKNOWN' ? 'Provider status awaiting review' : remaining == null ? '—' : remaining === 0 ? 'Offer deadline passed - checking its status' : `${Math.floor(remaining / 3600000)}h ${Math.floor(remaining / 60000) % 60}m ${Math.floor(remaining / 1000) % 60}s`
  const canRespond = !loading && offer.can_respond && remaining > 0
  return <article className="best-offer-card">
    <div className="best-offer-image">{listing.image_url ? <img src={listing.image_url} alt={listing.title || 'Product'} loading="lazy" /> : <span>No image</span>}</div>
    <div className="best-offer-product">
      <div className="bo-card-badges"><span className={`best-offer-status bo-status-${status.toLowerCase()} bo-group-${group.toLowerCase()}`}>{offer.display_status || bestOfferStatusLabel(status)}</span><span className="bo-lifecycle-label">{bestOfferGroupLabels[group]}</span>
      <span className="bo-offer-role">{roleLabel}</span></div>
      {!offer.status_verified ? <small className="bo-history-label">Saved from earlier records; current eBay status has not been confirmed</small> : null}
      <h2>{listing.title || `Item ${offer.listing_id}`}</h2>
      <dl className="bo-card-details">
        <div><dt>Synced account</dt><dd>{offer.account_name || '—'}</dd></div>
        {offer.offer_from || offer.offer_to ? <div><dt>Offer direction</dt><dd>{offer.offer_from || 'Unknown'} → {offer.offer_to || 'Unknown'}</dd></div> : null}
        <div><dt>Buyer</dt><dd>{offer.buyer || '—'}</dd></div>
        <div><dt>Item ID</dt><dd>{offer.listing_id || '—'}</dd></div>
        <div><dt>Offer ID</dt><dd>{offer.provider_offer_id || '—'}</dd></div>
        <div><dt>SKU</dt><dd>{listing.sku || '—'}</dd></div>
        <div><dt>Condition</dt><dd>{listing.condition || '—'}</dd></div>
        {offer.seller ? <div><dt>Seller</dt><dd>{offer.seller}</dd></div> : null}
      </dl>
      {offer.buyer_message ? <blockquote>{offer.buyer_message}</blockquote> : null}
      <div className="bo-card-dates"><span>{offer.received_at ? `Received: ${bestOfferDate(offer.received_at)}` : `Added to ACES: ${bestOfferDate(offer.first_seen_at)}`}</span>
      <span>{offer.status_verified ? 'Last checked with eBay' : 'Last processed in ACES'}: {bestOfferDate(offer.last_synced_at)}</span></div>
    </div>
    <div className="best-offer-prices">
      {offer.provider_role === 'Buyer' ? <a className="secondary-button bo-ebay-link" href={`https://www.ebay.com/itm/${encodeURIComponent(offer.listing_id)}`} target="_blank" rel="noreferrer">View listing on eBay</a> : null}
      <div className="bo-price-heading"><span>Offer amount</span>{prices.currency ? <span className="bo-currency">{prices.currency}</span> : null}</div><strong>{prices.amount}</strong>
      <span>Listing price</span><b>{prices.listingPrice}</b>
      {prices.listingNote ? <small className="bo-price-note">{prices.listingNote}</small> : null}
      <span>Quantity: {offer.quantity || '—'}</span>
      <time title={bestOfferDate(offer.expires_at)}>{countdown}</time>
      {offer.last_action ? <p className="best-offer-action-state">{offer.last_action.action}: {offer.last_action.state === 'SUCCEEDED' ? 'Confirmed by eBay; provider state awaits synchronization' : offer.last_action.state}</p> : null}
      {offer.reconciliation_required ? <small>Checking for a recent status change</small> : null}
      {canRespond ? <div className="best-offer-actions">
        <button className="primary-button" onClick={() => onAction(offer, 'Accept')}>Accept</button>
        <button className="secondary-button" onClick={() => onAction(offer, 'Counter')}>Counter Offer</button>
        <button className="secondary-button" onClick={() => onAction(offer, 'Decline')}>Decline</button>
      </div> : null}
    </div>
  </article>
}

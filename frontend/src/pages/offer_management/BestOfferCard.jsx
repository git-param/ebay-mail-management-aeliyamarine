import { bestOfferMoney, bestOfferDate } from './bestOfferFormat'

export default function BestOfferCard({ offer, now, onAction, loading }) {
  const listing = offer.listing || {}
  const remaining = offer.expires_at ? Math.max(0, new Date(offer.expires_at).getTime() - now) : null
  const countdown = remaining == null ? '—' : remaining === 0 ? 'Time elapsed; awaiting provider update' : `${Math.floor(remaining / 3600000)}h ${Math.floor(remaining / 60000) % 60}m ${Math.floor(remaining / 1000) % 60}s`
  const canRespond = !loading && offer.can_respond && remaining > 0
  return <article className="best-offer-card">
    <div className="best-offer-image">{listing.image_url ? <img src={listing.image_url} alt={listing.title || 'Product'} loading="lazy" /> : <span>No image</span>}</div>
    <div className="best-offer-product">
      <span className="best-offer-status">{offer.provider_status || 'Unknown provider state'}</span>
      <h2>{listing.title || `Item ${offer.listing_id}`}</h2>
      <p>Item #{offer.listing_id} · SKU: {listing.sku || '—'} · Condition: {listing.condition || '—'}</p>
      <p>Account: <strong>{offer.account_name}</strong> · Buyer: <strong>{offer.buyer || '—'}</strong></p>
      <small>Best Offer #{offer.provider_offer_id}</small>
      {offer.buyer_message ? <blockquote>{offer.buyer_message}</blockquote> : null}
      <p>{offer.received_at ? `Received: ${bestOfferDate(offer.received_at)}` : `First seen in ACES: ${bestOfferDate(offer.first_seen_at)}`}</p>
      <small>Last synchronized: {bestOfferDate(offer.last_synced_at)}</small>
    </div>
    <div className="best-offer-prices">
      <span>Buyer offer</span><strong>{bestOfferMoney(offer.amount, offer.currency)}</strong>
      <span>Listed price</span><b>{bestOfferMoney(listing.price, listing.currency)}</b>
      <span>Quantity: {offer.quantity || '—'}</span>
      <time title={bestOfferDate(offer.expires_at)}>{countdown}</time>
      {offer.last_action ? <p className="best-offer-action-state">{offer.last_action.action}: {offer.last_action.state === 'SUCCEEDED' ? 'Confirmed by eBay; provider state awaits synchronization' : offer.last_action.state}</p> : null}
      {offer.reconciliation_required ? <small>Awaiting reconciliation</small> : null}
      {canRespond ? <div className="best-offer-actions">
        <button className="primary-button" onClick={() => onAction(offer, 'Accept')}>Accept</button>
        <button className="secondary-button" onClick={() => onAction(offer, 'Counter')}>Counter Offer</button>
        <button className="secondary-button" onClick={() => onAction(offer, 'Decline')}>Decline</button>
      </div> : null}
    </div>
  </article>
}

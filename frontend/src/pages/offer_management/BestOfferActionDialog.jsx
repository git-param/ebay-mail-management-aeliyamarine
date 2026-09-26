import { useRef, useState } from 'react'
import { respondToBestOffer } from '../../services/ebayBestOfferApi'
import { bestOfferMoney } from './bestOfferFormat'

export default function BestOfferActionDialog({ offer, action, onClose, onDone }) {
  const [amount, setAmount] = useState('')
  const [quantity, setQuantity] = useState(offer.quantity || '')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const key = useRef(crypto.randomUUID())
  const dispatching = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (dispatching.current) return
    dispatching.current = true
    setBusy(true)
    setError('')
    try {
      const result = await respondToBestOffer(offer.id, { action, expected_version: offer.version,
        idempotency_key: key.current, message: message || null,
        ...(action === 'Counter' ? { amount, quantity: Number(quantity) } : {}) })
      onDone(result)
    } catch (err) {
      setError(`${err.message} Refresh the offer before another action; this request will not be resent automatically.`)
    } finally { setBusy(false) }
  }
  return <div className="modal-backdrop"><section className="modal-panel best-offer-dialog" role="dialog" aria-modal="true" aria-labelledby="best-offer-action-title">
    <h2 id="best-offer-action-title">{action === 'Counter' ? 'Send Counter Offer' : `${action} Offer`}</h2>
    <p>{offer.listing?.title || `Item ${offer.listing_id}`}</p>
    <p>Buyer: {offer.buyer} · Buyer offer: {bestOfferMoney(offer.amount, offer.currency)}</p>
    <p>Listed price: {bestOfferMoney(offer.listing?.price, offer.listing?.currency)}</p>
    {action === 'Accept' ? <p>Accept this buyer offer? Payment completion will be shown after eBay confirms its provider state.</p> : null}
    {action === 'Decline' ? <p>Decline this offer?</p> : null}
    <form onSubmit={submit}>
      {action === 'Counter' ? <div className="best-offer-form-grid">
        <label className="field"><span>Counter total ({offer.currency}) for the quantity below</span><input type="number" min="0.01" step="0.01" required value={amount} disabled={busy} onChange={e => setAmount(e.target.value)} /></label>
        <label className="field"><span>Quantity</span><input type="number" min="1" max={offer.quantity} step="1" required value={quantity} disabled={busy} onChange={e => setQuantity(e.target.value)} /></label>
      </div> : null}
      <label className="field"><span>Seller response (optional, 250 characters)</span><textarea maxLength={250} value={message} disabled={busy} onChange={e => setMessage(e.target.value)} /></label>
      {error ? <p role="alert" className="form-message error">{error}</p> : null}
      <div className="modal-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy || Boolean(error)}>{busy ? 'Sending…' : action === 'Counter' ? 'Send Counter Offer' : `${action} Offer`}</button></div>
    </form>
  </section></div>
}

import { useEffect, useState } from 'react'
import { fetchCurrentOffers, fetchBestOfferAccounts } from '../../services/ebayBestOfferApi'
import BestOfferCard from './BestOfferCard'
import BestOfferActionDialog from './BestOfferActionDialog'
import './best_offers.css'

export default function CurrentOffers() {
  const [filters, setFilters] = useState({ account_id: '', status: '', search: '', buyer: '', item_id: '', sort: 'expiring', page: 1, page_size: 25 })
  const [data, setData] = useState({ items: [], summary: {}, statuses: [], total: 0 })
  const [accounts, setAccounts] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(() => Date.now())
  const [dialog, setDialog] = useState(null)
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    fetchBestOfferAccounts().then(result => { if (active) setAccounts(result.items) }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      setLoading(true)
      fetchCurrentOffers(filters).then(result => { if (active) { setData(result); setError('') } })
        .catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setLoading(false) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [filters, revision])
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  function filter(name, value) { setFilters(current => ({ ...current, [name]: value, page: 1 })) }
  return <section className="best-offers-page" aria-label="Current eBay seller offers">
    <div className="best-offers-heading"><div><h1>Current Offers</h1><p>Synchronized seller offers · Browsing uses stored ACES data</p></div><button className="secondary-button" onClick={() => setRevision(r => r + 1)}>Refresh view</button></div>
    <div className="best-offer-summary">{[['Active Offers', (data.summary.Active || 0)+(data.summary.Pending || 0)], ['Expiring Soon', data.summary.ExpiringSoon || 0], ['Countered', data.summary.Countered || 0], ['Accepted', data.summary.Accepted || 0], ['Declined', data.summary.Declined || 0], ['Expired', data.summary.Expired || 0]].map(([label, count]) => <div key={label}><span>{label}</span><strong>{count}</strong></div>)}</div>
    <div className="best-offer-filters">
      <label className="field"><span>Account</span><select value={filters.account_id} onChange={e => filter('account_id', e.target.value)}><option value="">All Accounts</option>{accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <label className="field"><span>Provider status</span><select value={filters.status} onChange={e => filter('status', e.target.value)}><option value="">All</option>{data.statuses.map(status => <option key={status}>{status}</option>)}</select></label>
      <label className="field"><span>Search title, SKU, Item, offer ID or buyer</span><input value={filters.search} onChange={e => filter('search', e.target.value)} /></label>
      <label className="field"><span>Buyer</span><input value={filters.buyer} onChange={e => filter('buyer', e.target.value)} /></label>
      <label className="field"><span>Item ID</span><input value={filters.item_id} onChange={e => filter('item_id', e.target.value)} /></label>
      <label className="field"><span>Sort</span><select value={filters.sort} onChange={e => filter('sort', e.target.value)}><option value="expiring">Expiring Soonest</option><option value="newest">Newest first seen</option><option value="amount">Offer Amount</option><option value="listing_price">Listing Price</option></select></label>
    </div>
    {error ? <p role="alert" className="form-message error">{error}</p> : null}
    {notice ? <p role="status" className="form-message">{notice}</p> : null}
    {loading ? <p role="status">Loading stored offers…</p> : null}
    {!loading && !data.items.length ? <div className="best-offer-empty">No verified seller offers match. Admin or Ops Manager can synchronize accounts in Config.</div> : null}
    {data.items.map(offer => <BestOfferCard key={offer.id} offer={offer} now={now} loading={loading} onAction={(selected, action) => setDialog({ offer: selected, action })} />)}
    <div className="pagination-bar"><span>{data.total} offers · Page {filters.page}</span><div><select aria-label="Offers per page" value={filters.page_size} onChange={e => filter('page_size', Number(e.target.value))}>{[10,25,50,100].map(size => <option key={size}>{size}</option>)}</select><button className="secondary-button" disabled={filters.page <= 1} onClick={() => setFilters(f => ({ ...f, page: f.page-1 }))}>Previous</button><button className="secondary-button" disabled={filters.page * filters.page_size >= data.total} onClick={() => setFilters(f => ({ ...f, page: f.page+1 }))}>Next</button></div></div>
    {dialog ? <BestOfferActionDialog key={`${dialog.offer.id}-${dialog.action}`} {...dialog} onClose={() => setDialog(null)} onDone={result => { setDialog(null); setNotice(`${result.action}: ${result.state === 'SUCCEEDED' ? 'Confirmed by eBay. Provider state will update after synchronization.' : result.state}`); setRevision(r => r+1) }} /> : null}
  </section>
}

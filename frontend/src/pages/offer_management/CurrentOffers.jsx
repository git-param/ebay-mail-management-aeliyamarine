import { useEffect, useState } from 'react'
import { fetchCurrentOffers, fetchBestOfferAccounts } from '../../services/ebayBestOfferApi'
import BestOfferCard from './BestOfferCard'
import BestOfferActionDialog from './BestOfferActionDialog'
import { bestOfferStatusKey, bestOfferStatusLabel, bestOfferStatusGroup, bestOfferGroupLabels } from './bestOfferFormat'
import './best_offers.css'

const defaultFilters = { account_id: '', role: '', status: '', lifecycle: '', view: 'current', search: '', buyer: '', item_id: '', sort: 'newest', page: 1, page_size: 25 }

export default function CurrentOffers() {
  const [filters, setFilters] = useState(defaultFilters)
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
  function filter(name, value) { setLoading(true); setFilters(current => ({ ...current, [name]: value, ...(name === 'lifecycle' ? { status: '' } : {}), ...(name === 'view' ? { status: '', lifecycle: '', role: '' } : {}), page: 1 })) }
  const statuses = [...new Set((data.statuses || []).map(bestOfferStatusKey).filter(Boolean))].sort()
  const summary = Object.entries(data.summary || {}).reduce((counts, [status, count]) => {
    const key = bestOfferStatusKey(status)
    counts[key] = (counts[key] || 0) + Number(count || 0)
    return counts
  }, {})
  const groups = data.status_groups || Object.entries(summary).reduce((counts, [status, count]) => {
    if (status !== 'EXPIRINGSOON') {
      const key = bestOfferStatusGroup(status)
      counts[key] = (counts[key] || 0) + count
    }
    return counts
  }, {})
  const statusOptions = data.status_options || statuses.map(value => ({ value, label: bestOfferStatusLabel(value), group: bestOfferStatusGroup(value) }))
  const hasFilters = ['account_id', 'role', 'status', 'lifecycle', 'search', 'buyer', 'item_id'].some(key => filters[key])
  const hasDetailFilters = ['role', 'status', 'lifecycle', 'search', 'buyer', 'item_id'].some(key => filters[key])
  const totalPages = Math.max(1, Math.ceil(data.total / filters.page_size))
  const first = data.total ? (filters.page - 1) * filters.page_size + 1 : 0
  const last = Math.min(filters.page * filters.page_size, data.total)
  return <section className="best-offers-page" aria-label="All eBay offers">
    <div className="best-offers-heading"><div><span className="bo-eyebrow">OFFER MANAGEMENT</span><h1>{filters.view === 'history' ? 'Offer history' : 'Current offers'}</h1><p>{filters.view === 'history' ? 'Latest saved offer for each buyer and item. Historical records may no longer appear on eBay.' : 'Latest offer for each buyer and item from the last complete account sync.'}</p></div><button className="secondary-button" disabled={loading} onClick={() => { setLoading(true); setRevision(r => r + 1) }}>{loading ? 'Refreshing…' : 'Refresh view'}</button></div>
    <div className="bo-view-meta"><div className="bo-view-switch" role="group" aria-label="Offer view"><button aria-pressed={filters.view === 'current'} onClick={() => filter('view', 'current')}>Current offers</button><button aria-pressed={filters.view === 'history'} onClick={() => filter('view', 'history')}>Saved history</button></div>
    {!loading && filters.view === 'current' && data.snapshots?.length ? <p className="bo-snapshot-note">Most recent complete account sync: {new Date(Math.max(...data.snapshots.map(snapshot => new Date(snapshot.synced_at).getTime()))).toLocaleString()}</p> : null}
    <details className="bo-coverage-note"><summary>About this view</summary><p>Current offers are replaced after a complete eBay account scan. An empty result clears the account's current offers; an incomplete scan keeps the previous view. Saved history is available separately. Seller-initiated discounts require the separate eBay notification feed.</p></details>
    </div>
    <div className="best-offer-summary">{[['Open offers', groups.OPEN || 0, 'active'], ['Expiring soon', summary.EXPIRINGSOON || 0, 'expiring'], ['Waiting for buyer', groups.AGREED || 0, 'countered'], ['Completed', groups.COMPLETED || 0, 'accepted'], ['Closed', groups.CLOSED || 0, 'declined'], ['Other statuses', groups.UNKNOWN || 0, 'expired']].map(([label, count, tone]) => <div key={label} className={`bo-summary-${tone}`}><span>{label}</span><strong>{count.toLocaleString()}</strong></div>)}</div>
    <div className="best-offer-filters">
      <div className="bo-filter-heading"><div><h2>Filter offers</h2><span>Find an offer by account, status, or item details.</span></div><button className="bo-text-button" disabled={!hasFilters} onClick={() => { setLoading(true); setFilters(current => ({ ...defaultFilters, view: current.view, page_size: current.page_size })) }}>Clear filters</button></div>
      <div className="bo-lifecycle-filters" role="group" aria-label="Offer lifecycle"><button aria-pressed={!filters.lifecycle} onClick={() => filter('lifecycle', '')}>All offers</button>{Object.entries(bestOfferGroupLabels).map(([value, label]) => <button key={value} aria-pressed={filters.lifecycle === value} onClick={() => filter('lifecycle', value)}>{label}</button>)}</div>
      <label className="field bo-search-field"><span>Search offers</span><input type="search" placeholder="Title, SKU, item ID, offer ID or buyer" value={filters.search} onChange={e => filter('search', e.target.value)} /></label>
      <label className="field"><span>Account</span><select value={filters.account_id} onChange={e => filter('account_id', e.target.value)}><option value="">All Accounts</option>{accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <label className="field"><span>Offer status</span><select value={filters.status} onChange={e => filter('status', e.target.value)}><option value="">All statuses</option>{Object.entries(bestOfferGroupLabels).filter(([group]) => (!filters.lifecycle || filters.lifecycle === group) && statusOptions.some(option => option.group === group)).map(([group, label]) => <optgroup key={group} label={label}>{statusOptions.filter(option => option.group === group).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</optgroup>)}</select></label>
      <details className="bo-advanced-filters">
        <summary>More filters{['role', 'buyer', 'item_id'].some(key => filters[key]) ? ' (active)' : ''}</summary>
        <div className="bo-advanced-grid">
      <label className="field"><span>Account role</span><select value={filters.role} onChange={e => filter('role', e.target.value)}><option value="">Buyer and seller</option><option value="Buyer">Buyer</option><option value="Seller">Seller</option><option value="Unknown">Unverified history</option></select></label>
      <label className="field"><span>Buyer</span><input placeholder="Buyer username" value={filters.buyer} onChange={e => filter('buyer', e.target.value)} /></label>
      <label className="field"><span>Item ID</span><input placeholder="Enter an eBay item ID" value={filters.item_id} onChange={e => filter('item_id', e.target.value)} /></label>
        </div>
      </details>
    </div>
    {error ? <p role="alert" className="form-message error">{error}</p> : null}
    {notice ? <p role="status" className="form-message">{notice}</p> : null}
    <div className="bo-offers-toolbar"><p role="status">{loading ? 'Loading offers…' : `${data.total.toLocaleString()} offers${hasFilters ? ' matching your filters' : ''}`}</p><label className="bo-sort"><span>Sort by</span><select value={filters.sort} onChange={e => filter('sort', e.target.value)}><option value="expiring">Expiring soonest</option><option value="newest">Newest first seen</option><option value="amount">Highest offer amount</option><option value="listing_price">Highest listing price</option></select></label></div>
    {!loading && !data.items.length ? <div className="best-offer-empty">{hasDetailFilters ? 'No offers match these filters.' : filters.view === 'history' ? 'No saved offer history.' : data.snapshots?.length ? 'No current offers were returned by the last complete eBay sync.' : 'No current account snapshot yet. Synchronize accounts in Config to fetch offers from eBay.'}</div> : null}
    <div className="bo-offers-list" aria-busy={loading}>{data.items.map(offer => <BestOfferCard key={offer.id} offer={offer} now={now} loading={loading} onAction={(selected, action) => setDialog({ offer: selected, action })} />)}</div>
    <div className="bo-pagination"><span>Showing {first}–{last} of {data.total.toLocaleString()} offers</span><div><select aria-label="Offers per page" value={filters.page_size} onChange={e => filter('page_size', Number(e.target.value))}>{[10,25,50,100].map(size => <option key={size} value={size}>{size} per page</option>)}</select><button className="secondary-button" disabled={loading || filters.page <= 1} onClick={() => { setLoading(true); setFilters(f => ({ ...f, page: f.page-1 })) }}>Previous</button><span>Page {filters.page} of {totalPages}</span><button className="secondary-button" disabled={loading || filters.page >= totalPages} onClick={() => { setLoading(true); setFilters(f => ({ ...f, page: f.page+1 })) }}>Next</button></div></div>
    {dialog ? <BestOfferActionDialog key={`${dialog.offer.id}-${dialog.action}`} {...dialog} onClose={() => setDialog(null)} onDone={result => { setDialog(null); setNotice(`${result.action}: ${result.state === 'SUCCEEDED' ? 'Confirmed by eBay. Provider state will update after synchronization.' : result.state}`); setRevision(r => r+1) }} /> : null}
  </section>
}

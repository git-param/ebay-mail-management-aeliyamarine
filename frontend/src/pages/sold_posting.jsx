import { useCallback, useEffect, useMemo, useState } from 'react'
import AppLayout, { Icon } from '../layouts/app_layout'
import { fetchSoldPostingDetail, fetchSoldPostingOptions, fetchSoldPostingOrders, syncSoldPosting } from '../services/soldPostingApi'
import { normalizeRole } from '../utils/roles'

const emptyFilters = { page: 1, page_size: 50, sort_by: 'date_sold', sort_direction: 'desc' }

function money(value, currency) {
  if (value === null || value === undefined || value === '') return '-'
  return `${currency || ''} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function dt(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString()
}

function StatusBadge({ value }) {
  return <span className={`status-badge status-${String(value || 'other').toLowerCase().replaceAll('_', '-')}`}>{String(value || 'OTHER').replaceAll('_', ' ')}</span>
}

function CopyValue({ value }) {
  if (!value) return <span>-</span>
  return <button className="copy-chip" type="button" title="Copy" onClick={() => navigator.clipboard?.writeText(value)}>{value}</button>
}

function DetailDrawer({ order, onClose }) {
  if (!order) return null
  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="user-drawer sold-detail-drawer">
        <div className="drawer-header"><h2>Order {order.order_id}</h2><button className="icon-button" type="button" onClick={onClose}><Icon name="close" /></button></div>
        <div className="drawer-profile"><h3>{order.ebay_account_name}</h3><p>{order.buyer_username || 'Buyer hidden'} - {dt(order.creation_date)}</p><StatusBadge value={order.normalized_status} /></div>
        <section className="drawer-section"><h3>Payment</h3><p>Status: {order.order_payment_status || '-'}</p><p>Paid: {dt(order.payment_date)}</p><p>Total: {money(order.order_total, order.currency)} - Due seller: {money(order.total_due_seller, order.currency)}</p></section>
        <section className="drawer-section"><h3>Fulfillment</h3><p>Status: {order.order_fulfillment_status || '-'}</p><p>Carrier: {order.shipping_carrier_code || '-'} - Service: {order.shipping_service_code || '-'}</p><p>Tracking: {order.tracking_number || '-'}</p><p>Ship by: {dt(order.ship_by_date)}</p></section>
        <section className="drawer-section"><h3>Line Items</h3>{(order.line_items || []).map((item) => <p key={item.id}>{item.title || 'Untitled'} - <CopyValue value={item.sku || 'No SKU'} /> - Qty {item.quantity || 0} - {money(item.line_item_total, item.currency)}</p>)}</section>
      </aside>
    </div>
  )
}

export default function SoldPosting({ currentUser, onLogout }) {
  const isAdmin = normalizeRole(currentUser?.role) === 'ADMIN'
  const [filters, setFilters] = useState(emptyFilters)
  const [options, setOptions] = useState({ accounts: [], statuses: [] })
  const [data, setData] = useState({ items: [], total: 0, summary: {}, sync: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const [partialError, setPartialError] = useState('')
  const activeFilters = useMemo(() => filters, [filters])

  const load = useCallback(async (next = activeFilters) => {
    setLoading(true)
    try {
      const response = await fetchSoldPostingOrders(next)
      setData(response)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [activeFilters])

  useEffect(() => { fetchSoldPostingOptions().then(setOptions).catch(() => setOptions({ accounts: [], statuses: [] })) }, [])
  useEffect(() => { const timer = window.setTimeout(() => load(filters), 300); return () => window.clearTimeout(timer) }, [filters, load])

  function updateFilter(key, value) { setFilters((current) => ({ ...current, [key]: value, page: 1 })) }
  function updateMulti(key, event) { updateFilter(key, Array.from(event.target.selectedOptions).map((option) => option.value)) }
  async function openDetail(orderId) { setSelected(await fetchSoldPostingDetail(orderId)) }
  async function syncLatest() {
    setSyncing(true); setPartialError(''); setSyncResult(null)
    try {
      const result = await syncSoldPosting()
      setSyncResult(result)
      const failures = (result.results || []).filter((item) => !item.success)
      setPartialError(failures.length ? `${failures.length} account sync failed. Admin details are shown below.` : '')
      await load(filters)
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <AppLayout activePage="Sold Posting" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page sold-posting-page">
        <div className="page-header">
          <div><h1>Sold Posting</h1><p>{data.summary?.line_item_count || 0} matching line items - {data.summary?.order_count || 0} orders - {data.summary?.quantity_sold || 0} quantity sold - Last sync {dt(data.sync?.last_successful_sync_at)}</p></div>
          {isAdmin ? <button className="primary-button compact-action" type="button" disabled={syncing || data.sync?.is_running} onClick={syncLatest}>{syncing || data.sync?.is_running ? 'Syncing...' : 'Sync Latest Changes'}</button> : null}
        </div>
        {error ? <p className="form-message error">{error}</p> : null}
        {partialError ? <p className="form-message error">{partialError}</p> : null}
        {syncResult && isAdmin ? <section className="offer-bulk-bar">{syncResult.results.map((item) => <span key={item.account_id}>{item.account_name}: {item.success ? `${item.orders_received} orders, ${item.pages_fetched} pages` : item.error_message}</span>)}</section> : null}
        <section className="stats-grid">{[['Orders', data.summary?.order_count], ['Sold Items', data.summary?.line_item_count], ['Awaiting Shipment', data.summary?.awaiting_shipment], ['Shipped', data.summary?.shipped]].map(([title, value]) => <article className="stat-card" key={title}><div><p>{title}</p><strong>{value || 0}</strong></div></article>)}</section>
        <form className="analytics-filter-bar sold-filter-bar" onSubmit={(event) => event.preventDefault()}>
          <label className="field"><span>Date sold from</span><input type="date" value={filters.date_sold_from || ''} onChange={(event) => updateFilter('date_sold_from', event.target.value)} /></label>
          <label className="field"><span>Date sold to</span><input type="date" value={filters.date_sold_to || ''} onChange={(event) => updateFilter('date_sold_to', event.target.value)} /></label>
          <label className="field"><span>Date paid from</span><input type="date" value={filters.date_paid_from || ''} onChange={(event) => updateFilter('date_paid_from', event.target.value)} /></label>
          <label className="field"><span>Date paid to</span><input type="date" value={filters.date_paid_to || ''} onChange={(event) => updateFilter('date_paid_to', event.target.value)} /></label>
          <label className="field"><span>SKU</span><input value={filters.sku || ''} onChange={(event) => updateFilter('sku', event.target.value)} /></label>
          <label className="field"><span>Search</span><input type="search" value={filters.search || ''} onChange={(event) => updateFilter('search', event.target.value)} /></label>
          <label className="field"><span>Order ID</span><input value={filters.order_id || ''} onChange={(event) => updateFilter('order_id', event.target.value)} /></label>
          <label className="field"><span>Buyer</span><input value={filters.buyer_username || ''} onChange={(event) => updateFilter('buyer_username', event.target.value)} /></label>
          <label className="field"><span>Item ID</span><input value={filters.item_id || ''} onChange={(event) => updateFilter('item_id', event.target.value)} /></label>
          <label className="field"><span>eBay accounts</span><select multiple size="3" value={filters.account_ids || []} onChange={(event) => updateMulti('account_ids', event)}>{options.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
          <label className="field"><span>Statuses</span><select multiple size="3" value={filters.statuses || []} onChange={(event) => updateMulti('statuses', event)}>{options.statuses.map((status) => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}</select></label>
          <button className="secondary-button compact-action" type="button" onClick={() => setFilters(emptyFilters)}>Reset filters</button>
        </form>
        <section className="table-card">
          {loading ? <div className="empty-state">Loading sold items...</div> : data.items.length ? <div className="table-scroll sold-table-scroll"><table className="users-table sold-table"><thead><tr>{['Image', 'Account', 'Status', 'Order ID', 'SKU', 'Product', 'Buyer', 'Quantity', 'Item price', 'Shipping', 'Total', 'Date sold', 'Date paid', 'Item ID'].map((head) => <th key={head}>{head}</th>)}</tr></thead><tbody>{data.items.map((row) => <tr key={row.id} onClick={() => openDetail(row.order_id)}><td>{row.image_url ? <img className="sold-thumb" src={row.image_url} alt="" /> : <span className="sold-thumb placeholder"><Icon name="bag" /></span>}</td><td>{row.ebay_account_name}</td><td><StatusBadge value={row.status} /></td><td><CopyValue value={row.order_id} /></td><td><CopyValue value={row.sku} /></td><td className="sold-title">{row.product || '-'}</td><td>{row.buyer_username || '-'}</td><td>{row.quantity || 0}</td><td>{money(row.item_price, row.currency)}</td><td>{money(row.shipping, row.currency)}</td><td>{money(row.total, row.currency)}</td><td>{dt(row.date_sold)}</td><td>{dt(row.date_paid)}</td><td><CopyValue value={row.item_id} /></td></tr>)}</tbody></table></div> : <div className="empty-state">No sold items match these filters.</div>}
          <div className="pagination-bar"><span>Showing {data.items.length} of {data.total || 0}</span><div><button className="pagination-button" type="button" disabled={filters.page <= 1} onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}>Prev</button><button className="pagination-button" type="button" disabled={filters.page * filters.page_size >= (data.total || 0)} onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}>Next</button><select value={filters.page_size} onChange={(event) => setFilters((f) => ({ ...f, page: 1, page_size: Number(event.target.value) }))}><option>25</option><option>50</option><option>100</option></select></div></div>
        </section>
      </main>
      <DetailDrawer order={selected} onClose={() => setSelected(null)} />
    </AppLayout>
  )
}

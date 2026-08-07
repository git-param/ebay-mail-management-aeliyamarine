import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppLayout, { Icon } from '../../layouts/app_layout'
import { fetchSoldPostingDetail, fetchSoldPostingOptions, fetchSoldPostingOrders, markSoldPostingCopied, syncSoldPosting, updateSoldPostingLineItem } from '../../services/soldPostingApi'
import { normalizeRole } from '../../utils/roles'

import './sold_posting.css'

const emptyFilters = { page: 1, page_size: 50, sort_by: 'date_sold', sort_direction: 'desc' }
const periodOptions = [
  ['all', 'All time'],
  ['today', 'Today'],
  ['yesterday', 'Yesterday'],
  ['90', 'Last 90 days'],
  ['60', 'Last 60 days'],
  ['30', 'Last 30 days'],
  ['week', 'This week'],
  ['month', 'This month'],
  ['year', 'This year'],
  ['custom', 'Custom'],
]
const searchOptions = [
  ['buyer_username', 'Buyer username'],
  ['sku', 'SKU'],
  ['order_id', 'Order number'],
  ['item_id', 'Item ID'],
  ['search', 'Product / all'],
]

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

function labelize(value) {
  return String(value || '').replaceAll('_', ' ')
}

function isoDate(date) {
  return date.toISOString().slice(0, 10)
}

function periodRange(period) {
  const today = new Date()
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const start = new Date(end)
  if (period === 'all') return { date_sold_from: '', date_sold_to: '' }
  if (period === 'custom') return {}
  if (period === 'today') return { date_sold_from: isoDate(start), date_sold_to: isoDate(end) }
  if (period === 'yesterday') {
    start.setDate(start.getDate() - 1)
    return { date_sold_from: isoDate(start), date_sold_to: isoDate(start) }
  }
  if (period === 'week') start.setDate(start.getDate() - start.getDay())
  else if (period === 'month') start.setDate(1)
  else if (period === 'year') { start.setMonth(0); start.setDate(1) }
  else start.setDate(start.getDate() - (Number(period) || 90) + 1)
  return { date_sold_from: isoDate(start), date_sold_to: isoDate(end) }
}

function CopyValue({ value }) {
  if (!value) return <span>-</span>
  return <button className="copy-chip" type="button" title="Copy" onClick={(event) => { event.stopPropagation(); navigator.clipboard?.writeText(value) }}>{value}</button>
}

function FilterDropdown({ label, value, options, multiple = false, selected = [], onSelect, onToggle }) {
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef(null)
  const summary = multiple ? (selected.length ? `${label}: ${selected.length} selected` : `${label}: All`) : `${label}: ${value}`
  useEffect(() => {
    if (!open) return undefined
    function closeOnOutsideClick(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [open])
  return (
    <div className="sold-filter-dropdown" ref={dropdownRef}>
      <button className="sold-filter-trigger" type="button" onClick={() => setOpen((current) => !current)}>
        <span>{summary}</span><Icon name="chevron" />
      </button>
      {open ? (
        <div className="sold-filter-menu">
          {options.map((option) => {
            const optionValue = typeof option === 'string' ? option : option.value
            const optionLabel = typeof option === 'string' ? labelize(option) : option.label
            const checked = multiple ? selected.includes(optionValue) : value === optionLabel
            return (
              <button className={checked ? 'selected' : ''} type="button" key={optionValue} onClick={() => { multiple ? onToggle(optionValue) : onSelect(optionValue); if (!multiple) setOpen(false) }}>
                <span>{optionLabel}</span>{checked ? <Icon name="activate" /> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function copyAccountName(name) {
  const account = String(name || '').trim()
  return `Aeliya-${account || 'Account'}110`
}

function soldReferenceText(row) {
  const sku = row.sku || row.item_id || row.order_id || '-'
  const condition = row.condition || 'No condition'
  const quantity = row.quantity || 0
  return `Sold ref no ${sku} ${condition} ${quantity} Pc (${copyAccountName(row.ebay_account_name)})`
}

async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
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
        <section className="drawer-section"><h3>Line Items</h3>{(order.line_items || []).map((item) => <p key={item.id}>{item.title || 'Untitled'} - {item.condition || 'No condition'} - <CopyValue value={item.sku || 'No SKU'} /> - Qty {item.quantity || 0} - {money(item.line_item_total, item.currency)}</p>)}</section>
      </aside>
    </div>
  )
}

function EditSoldPostingModal({ row, statuses, saving, error, onChange, onCancel, onSave }) {
  if (!row) return null
  const field = (key, title, type = 'text') => (
    <label className="field">
      <span>{title}</span>
      <input type={type} value={row[key] || ''} onChange={(event) => onChange(key, event.target.value)} />
    </label>
  )
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel sold-edit-modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2>Edit Order</h2>
          <button className="icon-button" type="button" onClick={onCancel}><Icon name="close" /></button>
        </div>
        <div className="management-form sold-edit-form">
          {error ? <p className="form-message error">{error}</p> : null}
          <div className="sold-edit-columns">

            <section className="offer-form-section">
              <h3>Order</h3>

              <div className="sold-edit-field-list">
                <label className="field">
                  <span>Status</span>

                  <select
                    value={row.status || ''}
                    onChange={(event) => onChange('status', event.target.value)}
                  >
                    {statuses.map((status) => (
                      <option key={status} value={status}>
                        {status.replaceAll('_', ' ')}
                      </option>
                    ))}
                  </select>
                </label>

                {field('tracking_number', 'Tracking number')}
                {field('shipping_carrier_code', 'Carrier')}
                {field('shipping_service_code', 'Service')}
                {field('ship_by_date', 'Ship by', 'datetime-local')}
                {field('buyer_username', 'Buyer username')}
              </div>
            </section>


            <section className="offer-form-section">
              <h3>Line Item</h3>

              <div className="sold-edit-field-list">
                {field('sku', 'SKU')}
                {field('condition', 'Condition')}
                {field('title', 'Product title')}
                {field('quantity', 'Quantity', 'number')}

                {field('order_payment_status', 'Payment status')}
                {field('order_fulfillment_status', 'Fulfillment status')}
              </div>
            </section>

          </div>
          <div className="modal-actions">
            <button className="secondary-button" type="button" onClick={onCancel}>Cancel</button>
            <button className="primary-button" type="button" disabled={saving} onClick={onSave}>{saving ? 'Saving...' : 'Save Changes'}</button>
          </div>
        </div>
      </section>
    </div>
  )
}

export default function SoldPosting({ currentUser, onLogout }) {
  const isAdmin = normalizeRole(currentUser?.role) === 'ADMIN'
  const [period, setPeriod] = useState('90')
  const [customRange, setCustomRange] = useState({ date_sold_from: '', date_sold_to: '' })
  const [searchBy, setSearchBy] = useState('buyer_username')
  const [searchTerm, setSearchTerm] = useState('')
  const [filters, setFilters] = useState({ ...emptyFilters, ...periodRange('90'), statuses: ['AWAITING_SHIPMENT'] })
  const [options, setOptions] = useState({ accounts: [], statuses: [] })
  const [data, setData] = useState({ items: [], total: 0, summary: {}, sync: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [selected, setSelected] = useState(null)
  const [editTarget, setEditTarget] = useState(null)
  const [editError, setEditError] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [copiedToastId, setCopiedToastId] = useState(null)
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

  function toggleMulti(key, value) {
    setFilters((current) => {
      const selected = current[key] || []
      return { ...current, [key]: selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value], page: 1 }
    })
  }
  function changePeriod(value) {
    setPeriod(value)
    if (value === 'custom') {
      setCustomRange({
        date_sold_from: filters.date_sold_from || '',
        date_sold_to: filters.date_sold_to || '',
      })
      return
    }
    setFilters((current) => ({ ...current, ...periodRange(value), page: 1 }))
  }
  function updateCustomRange(key, value) {
    setCustomRange((current) => ({ ...current, [key]: value }))
  }
  function applyCustomRange() {
    setFilters((current) => ({ ...current, ...customRange, page: 1 }))
  }
  function changeSearchBy(value) {
    setSearchBy(value)
    setSearchTerm('')
    setFilters((current) => ({ ...current, buyer_username: '', sku: '', order_id: '', item_id: '', search: '', page: 1 }))
  }
  function updateSearchTerm(value) {
    setSearchTerm(value)
    setFilters((current) => ({ ...current, buyer_username: '', sku: '', order_id: '', item_id: '', search: '', [searchBy]: value, page: 1 }))
  }
  function resetFilters() {
    setPeriod('90')
    setCustomRange({ date_sold_from: '', date_sold_to: '' })
    setSearchBy('buyer_username')
    setSearchTerm('')
    setFilters({ ...emptyFilters, ...periodRange('90'), statuses: ['AWAITING_SHIPMENT'] })
  }
  async function openDetail(orderId) { setSelected(await fetchSoldPostingDetail(orderId)) }
  function openEdit(row, event) {
    event.stopPropagation()
    setEditError('')
    setEditTarget({
      ...row,
      title: row.product || '',
      ship_by_date: row.ship_by_date ? new Date(row.ship_by_date).toISOString().slice(0, 16) : '',
      tracking_number: row.tracking_number || '',
      shipping_carrier_code: row.shipping_carrier_code || '',
      shipping_service_code: row.shipping_service_code || '',
      order_payment_status: row.order_payment_status || '',
      order_fulfillment_status: row.order_fulfillment_status || '',
    })
  }
  function updateEditField(key, value) { setEditTarget((current) => ({ ...current, [key]: value })) }
  async function saveEdit() {
    setSavingEdit(true)
    setEditError('')
    try {
      await updateSoldPostingLineItem(editTarget.id, {
        status: editTarget.status,
        sku: editTarget.sku,
        condition: editTarget.condition,
        title: editTarget.title,
        quantity: editTarget.quantity === '' ? null : Number(editTarget.quantity),
        tracking_number: editTarget.tracking_number,
        shipping_carrier_code: editTarget.shipping_carrier_code,
        shipping_service_code: editTarget.shipping_service_code,
        ship_by_date: editTarget.ship_by_date ? new Date(editTarget.ship_by_date).toISOString() : null,
        order_payment_status: editTarget.order_payment_status,
        order_fulfillment_status: editTarget.order_fulfillment_status,
        buyer_username: editTarget.buyer_username,
      })
      setEditTarget(null)
      await load(filters)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }
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
  async function copySoldReference(row, event) {
    event.stopPropagation()
    try {
      await writeClipboard(soldReferenceText(row))
      const updated = await markSoldPostingCopied(row.id)
      setData((current) => ({
        ...current,
        items: (current.items || []).map((item) => (item.id === row.id ? { ...item, ...updated } : item)),
      }))
      setCopiedToastId(row.id)
      window.setTimeout(() => setCopiedToastId((current) => (current === row.id ? null : current)), 1400)
    } catch (err) {
      setError(err.message || 'Could not copy sold reference')
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
        <form className="sold-filter-bar compact-sold-filter-bar" onSubmit={(event) => event.preventDefault()}>
          <FilterDropdown label="Status" multiple selected={filters.statuses || []} options={(options.statuses || []).map((status) => ({ value: status, label: labelize(status) }))} onToggle={(value) => toggleMulti('statuses', value)} />
          <FilterDropdown label="Account" multiple selected={filters.account_ids || []} options={(options.accounts || []).map((account) => ({ value: account.id, label: account.name }))} onToggle={(value) => toggleMulti('account_ids', value)} />
          <FilterDropdown label="Period" value={(periodOptions.find(([value]) => value === period) || [period, period])[1]} options={periodOptions.map(([value, label]) => ({ value, label }))} onSelect={changePeriod} />
          {period === 'custom' ? (
            <div className="sold-custom-period">
              <label className="sold-date-filter"><span>From</span><input type="date" value={customRange.date_sold_from} onChange={(event) => updateCustomRange('date_sold_from', event.target.value)} /></label>
              <label className="sold-date-filter"><span>To</span><input type="date" value={customRange.date_sold_to} onChange={(event) => updateCustomRange('date_sold_to', event.target.value)} /></label>
              <button className="sold-custom-apply" type="button" onClick={applyCustomRange}>Apply</button>
            </div>
          ) : null}
          <FilterDropdown label="Search by" value={(searchOptions.find(([value]) => value === searchBy) || [searchBy, searchBy])[1]} options={searchOptions.map(([value, label]) => ({ value, label }))} onSelect={changeSearchBy} />
          <div className="sold-search-box"><input type="search" placeholder="Search..." value={searchTerm} onChange={(event) => updateSearchTerm(event.target.value)} /><button type="button" aria-label="Search"><Icon name="search" /></button></div>
          <button className="sold-reset-link" type="button" onClick={resetFilters}>Reset</button>
        </form>
        <section className="table-card">
          {loading ? <div className="empty-state">Loading sold items...</div> : data.items.length ? <div className="table-scroll sold-table-scroll"><table className="users-table sold-table"><thead><tr>{['Copy', 'Image', 'Account', 'Status', 'Order ID', 'SKU', 'Product', 'Condition', 'Buyer', 'Quantity', 'Item price', 'Shipping', 'Total', 'Date sold', 'Date paid', 'Item ID', 'Actions'].map((head) => <th key={head}>{head}</th>)}</tr></thead><tbody>{data.items.map((row) => <tr key={row.id} onClick={() => openDetail(row.order_id)}><td className="sold-copy-cell"><div className="sold-copy-actions"><span className={`copy-state-dot ${row.is_copied ? 'copied' : 'fresh'}`} title={row.is_copied ? `Copied${row.copied_at ? ` ${dt(row.copied_at)}` : ''}` : 'Not copied'} /><button className="icon-button sold-copy-button" type="button" title={soldReferenceText(row)} aria-label="Copy sold reference" onClick={(event) => copySoldReference(row, event)}><Icon name="copy" /></button>{copiedToastId === row.id ? <span className="sold-copied-label">Copied</span> : null}</div></td><td>{row.item_id ? <a href={`https://www.ebay.com/itm/${row.item_id}`} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>{row.image_url ? <img className="sold-thumb" src={row.image_url} alt="" /> : <span className="sold-thumb placeholder"><Icon name="bag" /></span>}</a> : row.image_url ? <img className="sold-thumb" src={row.image_url} alt="" /> : <span className="sold-thumb placeholder"><Icon name="bag" /></span>}</td><td>{row.ebay_account_name}</td><td><StatusBadge value={row.status} /></td><td><CopyValue value={row.order_id} /></td><td><CopyValue value={row.sku} /></td><td className="sold-title"><span>{row.product || '-'}</span></td><td>{row.condition || '-'}</td><td>{row.buyer_username || '-'}</td><td>{row.quantity || 0}</td><td>{money(row.item_price, row.currency)}</td><td>{money(row.shipping, row.currency)}</td><td>{money(row.total, row.currency)}</td><td>{dt(row.date_sold)}</td><td>{dt(row.date_paid)}</td><td><CopyValue value={row.item_id} /></td><td><button className="icon-button offer-action-icon offer-action-edit" type="button" title="Edit order" aria-label="Edit order" onClick={(event) => openEdit(row, event)}><Icon name="edit" /></button></td></tr>)}</tbody></table></div> : <div className="empty-state">No sold items match these filters.</div>}
          <div className="pagination-bar"><span>Showing {data.items.length} of {data.total || 0}</span><div><button className="pagination-button" type="button" disabled={filters.page <= 1} onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}>Prev</button><button className="pagination-button" type="button" disabled={filters.page * filters.page_size >= (data.total || 0)} onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}>Next</button><select value={filters.page_size} onChange={(event) => setFilters((f) => ({ ...f, page: 1, page_size: Number(event.target.value) }))}><option>25</option><option>50</option><option>100</option></select></div></div>
        </section>
      </main>
      <DetailDrawer order={selected} onClose={() => setSelected(null)} />
      <EditSoldPostingModal row={editTarget} statuses={options.statuses || []} saving={savingEdit} error={editError} onChange={updateEditField} onCancel={() => setEditTarget(null)} onSave={saveEdit} />
    </AppLayout>
  )
}


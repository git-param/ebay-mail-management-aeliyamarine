import { useEffect, useMemo, useRef, useState } from 'react'
import AppLayout, { Icon } from '../../layouts/app_layout'
import { fetchEbayAccounts } from '../../services/ebayAccountApi'
import { fetchUsers } from '../../services/userApi'
import './offer_management.css'
import {
  checkOfferListingDuplicate,
  createOfferEntry,
  bulkDeleteOfferEntries,
  deleteOfferEntry,
  exportOfferEntries,
  fetchOfferEntries,
  fetchOfferHistory,
  fetchOfferLookups,
  fetchOfferSummary,
  importOfferEntriesExcel,
  lookupOfferListing,
  updateOfferEntry,
} from '../../services/offerManagementApi'
import { normalizeRole } from '../../utils/roles'

const blankEntry = {
  offer_date: new Date().toISOString().slice(0, 10),
  ebay_account_id: '',
  listing_id: '',
  listing_url: '',
  sku: '',
  product_title: '',
  condition: '',
  listing_quantity: '',
  offer_quantity: 1,
  currency: 'USD',
  listed_price: '',
  revised_price: '',
  automated_offer_price: '',
  buyer_offer_price: '',
  offered_price: '',
  counteroffer_price: '',
  final_price: '',
  buyer_id: '',
  status: 'OPEN',
  outcome: 'PENDING',
  is_vip_lead: false,
  next_offer_followup: '',
  follow_up_1_notes: '',
  follow_up_2_notes: '',
  remarks: '',
  related_conversation_id: '',
  related_offer_id: '',
}

const OFFER_STATUSES = ['OPEN', 'CLOSED']
const OFFER_OUTCOMES = [
  'DONE',
  'IGNORE',
  'SOLD',
  'NOT_ABLE_TO_MATCH_THE_PRICE',
]

function normalizeOfferForm(entry) {
  const next = entry ? { ...blankEntry, ...entry } : { ...blankEntry }

  if (!OFFER_STATUSES.includes(next.status)) {
    next.status = 'OPEN'
  }

  if (
    next.outcome !== 'PENDING'
    && !OFFER_OUTCOMES.includes(next.outcome)
  ) {
    next.outcome = 'PENDING'
  }

  if (next.status === 'CLOSED' && next.outcome === 'PENDING') {
    next.outcome = ''
  }

  return next
}

function cleanPayload(form) {
  const payload = { ...form }
  if (payload.status === 'CLOSED') {
    payload.next_offer_followup = null
  }
  if (payload.status !== 'CLOSED' && !payload.outcome) {
    payload.outcome = 'PENDING'
  }
  if (payload.currency === 'OTHER') {
    payload.currency = String(payload.custom_currency || '').trim().toUpperCase()
  }
  delete payload.custom_currency
  Object.keys(payload).forEach((key) => {
    if (payload[key] === '') payload[key] = null
  })
  ;['listing_quantity', 'offer_quantity'].forEach((key) => {
    if (payload[key] !== null && payload[key] !== undefined) payload[key] = Number(payload[key])
  })
  return payload
}

function money(value, currency) {
  if (value === null || value === undefined || value === '') return '—'
  return `${currency || ''} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function label(value) {
  return String(value || '—').replaceAll('_', ' ')
}

function todayDateValue() {
  const today = new Date()
  const offset = today.getTimezoneOffset() * 60000
  return new Date(today.getTime() - offset).toISOString().slice(0, 10)
}

function Badge({ value, tone = '' }) {
  return <span className={`status-badge status-${tone || String(value).toLowerCase().replaceAll('_', '-')}`}>{label(value)}</span>
}

function ActionIcon({ title, icon, tone = 'neutral', onClick, href, external = false }) {
  const content = <Icon name={icon} />
  if (href) {
    return <a className={`icon-button offer-action-icon offer-action-${tone}`} href={href} title={title} aria-label={title} target={external ? '_blank' : undefined} rel={external ? 'noreferrer' : undefined}>{content}</a>
  }
  return <button className={`icon-button offer-action-icon offer-action-${tone}`} type="button" title={title} aria-label={title} onClick={onClick}>{content}</button>
}

function OfferForm({ entry, lookups, accounts, onCancel, onSaved }) {
  const [form, setForm] = useState(() => normalizeOfferForm(entry))
  const [lookupText, setLookupText] = useState(entry?.listing_id || '')
  const [lookupResult, setLookupResult] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [duplicateNotice, setDuplicateNotice] = useState(null)
  const accountOptions = useMemo(() => {
    const items = [...accounts]
    if (form.ebay_account_id && !items.some((account) => account.id === form.ebay_account_id)) {
      items.unshift({
        id: form.ebay_account_id,
        account_name: form.ebay_account_name || 'Fetched account',
      })
    }
    return items
  }, [accounts, form.ebay_account_id, form.ebay_account_name])

  function update(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value }

      if (key === 'status') {
        if (value === 'CLOSED') {
          next.next_offer_followup = ''
          if (next.outcome === 'PENDING') {
            next.outcome = ''
          }
        } else if (!next.outcome) {
          next.outcome = 'PENDING'
        }
      }

      return next
    })
  }

  function applyLookup(data) {
    const selected = data.selected || data.details || {}
    setForm((current) => ({ ...current, ...selected, listing_id: data.listing_id, listing_url: data.listing_url || selected.listing_url || current.listing_url }))
  }

  async function fetchDetails() {
    setFetching(true)
    setError('')
    setDuplicateNotice(null)
    try {
      const data = await lookupOfferListing(lookupText)
      setLookupResult(data)
      applyLookup(data)
      if (data.existing_entry) {
        setDuplicateNotice(data.existing_entry)
      }
    } catch (err) {
      setLookupResult(null)
      setError(err.message)
    } finally {
      setFetching(false)
    }
  }

  async function save(preview = false) {
    setSaving(true)
    setError('')
    try {
      const nextForm = {
        ...form,
        listing_id: form.listing_id || lookupText,
        listing_url: form.listing_url || (lookupText && /^\d+$/.test(lookupText) ? `https://www.ebay.com/itm/${lookupText}` : ''),
      }
      const payload = cleanPayload(nextForm)
      if (!payload.currency) {
        throw new Error('Enter a currency code.')
      }
      if (payload.status === 'CLOSED') {
        if (!payload.outcome || payload.outcome === 'PENDING') {
          throw new Error('Select an outcome before closing the offer.')
        }
        if (!String(payload.remarks || '').trim()) {
          throw new Error('Remarks are required before closing the offer.')
        }
      }
      if (!entry?.id && payload.listing_id) {
        const duplicate = await checkOfferListingDuplicate(payload.listing_id).catch(() => null)
        if (duplicate?.exists) {
          setDuplicateNotice(duplicate)
        }
      }
      const saved = entry?.id ? await updateOfferEntry(entry.id, payload) : await createOfferEntry(payload)
      onSaved(saved, preview)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const field = (key, title, type = 'text') => (
    <label className="field">
      <span>{title}</span>
      <input type={type === 'number' ? 'text' : type} inputMode={type === 'number' ? 'decimal' : undefined} value={form[key] || ''} onChange={(event) => update(key, event.target.value)} />
    </label>
  )

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel offer-entry-modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2>{entry ? 'Edit Offer Entry' : 'New Offer Entry'}</h2>
          <button className="icon-button" type="button" onClick={onCancel}><Icon name="close" /></button>
        </div>
        {duplicateNotice ? (
          <div className="offer-duplicate-toast" role="status">
            Offer for this item already exists with buyer name = {duplicateNotice.buyer_id || 'Unknown'}. Edit entry #{duplicateNotice.entry_number} if needed, or continue creating a new offer.
          </div>
        ) : null}
        <div className="management-form offer-entry-form">
          <section className="offer-form-section">
            <h3>Listing Lookup</h3>
            <div className="form-grid two">
              <label className="field"><span>Listing ID or eBay URL</span><input value={lookupText} onChange={(event) => setLookupText(event.target.value)} /></label>
              <button className="secondary-button compact-action action-button action-load" type="button" disabled={fetching || !lookupText} onClick={fetchDetails}>{fetching ? 'Fetching...' : 'Fetch Details'}</button>
            </div>
            {error ? <p className="form-message error">{error}</p> : lookupResult ? <p className="form-message success">{lookupResult.message}</p> : null}
            {lookupResult?.matches?.length > 1 ? <div className="offer-match-list">{lookupResult.matches.map((match) => <button key={match.offer_id} type="button" className="secondary-button compact-action" onClick={() => setForm((current) => ({ ...current, ebay_account_id: match.seller_account_id || current.ebay_account_id, ebay_account_name: match.seller_account || current.ebay_account_name, buyer_id: match.buyer_id || '', buyer_offer_price: match.offer_amount || '', automated_offer_price: match.offer_type === 'OUTGOING' ? match.offer_amount || '' : current.automated_offer_price, currency: match.currency || current.currency, related_offer_id: match.offer_id, related_conversation_id: match.related_conversation_id || current.related_conversation_id }))}>{match.buyer_id || 'Unknown buyer'} · {match.offer_type || 'Offer'} · {money(match.offer_amount, match.currency)} · {match.seller_account || 'Account'} · {match.offer_status}</button>)}</div> : null}
          </section>
          <section className="offer-form-section">
            <h3>Listing Details</h3>
            <div className="form-grid">
              <label className="field"><span>Seller account</span><select value={form.ebay_account_id || ''} onChange={(event) => update('ebay_account_id', event.target.value)}><option value="">Select</option>{accountOptions.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.store_name || account.ebay_username}</option>)}</select></label>
              {field('listing_id', 'Listing ID')}{field('sku', 'SKU')}{field('product_title', 'Product title')}{field('condition', 'Condition')}{field('listing_quantity', 'Listing quantity', 'number')}{field('listed_price', 'Listing price', 'number')}
              <label className="field"><span>Currency</span><select value={form.currency || 'USD'} onChange={(event) => update('currency', event.target.value)}>{(lookups.currencies || ['USD']).map((item) => <option key={item}>{item}</option>)}</select></label>
              {form.currency === 'OTHER' ? <label className="field"><span>Currency code</span><input value={form.custom_currency || ''} maxLength="10" onChange={(event) => update('custom_currency', event.target.value.toUpperCase())} /></label> : null}
              {field('listing_url', 'eBay URL')}
            </div>
          </section>
          <section className="offer-form-section">
            <h3>Offer Details</h3>
            <div className="form-grid">
              {field('offer_date', 'Offer date', 'date')}{field('buyer_id', 'Buyer ID')}{field('offer_quantity', 'Offer quantity', 'number')}{field('automated_offer_price', 'Automated offer', 'number')}{field('buyer_offer_price', 'Buyer offer', 'number')}{field('offered_price', 'Offered price')}{field('revised_price', 'Revised price', 'number')}{field('counteroffer_price', 'Counteroffer/best price', 'number')}{field('final_price', 'Final agreed price', 'number')}
              <label className="field"><span>Status</span><select value={form.status} onChange={(event) => update('status', event.target.value)}>{OFFER_STATUSES.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>
              <label className="field"><span>Outcome</span><select value={form.outcome || ''} required={form.status === 'CLOSED'} onChange={(event) => update('outcome', event.target.value)}><option value={form.status === 'CLOSED' ? '' : 'PENDING'}>{form.status === 'CLOSED' ? 'Select outcome' : 'Pending'}</option>{OFFER_OUTCOMES.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label>
              <label className="field"><span>Next offer follow-up</span><input type="date" value={form.next_offer_followup || ''} disabled={form.status === 'CLOSED'} onChange={(event) => update('next_offer_followup', event.target.value)} /></label>
              <label className="checkbox-field"><input type="checkbox" checked={Boolean(form.is_vip_lead)} onChange={(event) => update('is_vip_lead', event.target.checked)} /> VIP lead</label>
            </div>
          </section>
          <section className="offer-form-section"><h3>Follow-ups</h3><div className="form-grid two"><label className="field"><span>Follow-up 1</span><textarea value={form.follow_up_1_notes || ''} onChange={(event) => update('follow_up_1_notes', event.target.value)} /></label><label className="field"><span>Follow-up 2</span><textarea value={form.follow_up_2_notes || ''} onChange={(event) => update('follow_up_2_notes', event.target.value)} /></label></div></section>
          <section className="offer-form-section"><h3>Notes</h3><div className="form-grid two"><label className="field"><span>Remarks</span><textarea required={form.status === 'CLOSED'} value={form.remarks || ''} onChange={(event) => update('remarks', event.target.value)} /></label></div></section>
          <div className="modal-actions"><button className="secondary-button" type="button" onClick={onCancel}>Cancel</button><button className="secondary-button action-button action-preview" type="button" disabled={saving} onClick={() => save(true)}>Save and Preview</button><button className="primary-button action-button action-save" type="button" disabled={saving} onClick={() => save(false)}>{saving ? 'Saving...' : 'Save Entry'}</button></div>
        </div>
      </section>
    </div>
  )
}

function PreviewDrawer({ entry, history, canDelete, onClose, onEdit, onDelete }) {
  if (!entry) return null
  return <div className="drawer-backdrop" role="presentation"><aside className="user-drawer offer-preview-drawer"><div className="drawer-header"><h2>Entry #{entry.entry_number}</h2><button className="icon-button" type="button" onClick={onClose}><Icon name="close" /></button></div><div className="drawer-profile"><h3>{entry.product_title || entry.listing_id}</h3><p>{entry.agent_name || 'Agent'} · {entry.ebay_account_name}</p><div className="badge-row"><Badge value={entry.status} /><Badge value={entry.outcome} />{entry.is_high_value ? <Badge value="High Value" tone="active" /> : null}</div></div><section className="drawer-section"><h3>Listing</h3><p>{entry.listing_id} · {entry.sku || 'No SKU'}</p><p>{entry.condition || 'No condition'} · Qty {entry.listing_quantity || '—'}</p></section><section className="drawer-section"><h3>Price Progression</h3><p>{money(entry.listed_price, entry.currency)} → {money(entry.buyer_offer_price, entry.currency)} → {entry.offered_price || money(entry.counteroffer_price, entry.currency)} → {money(entry.final_price, entry.currency)}</p></section><section className="drawer-section"><h3>Follow-ups</h3><p>Next: {entry.next_offer_followup || '—'}</p><p>1: {entry.follow_up_1_notes || '—'}</p><p>2: {entry.follow_up_2_notes || '—'}</p></section><section className="drawer-section"><h3>Remarks</h3><p className="drawer-note">{entry.remarks || 'No remarks added.'}</p></section><section className="drawer-section"><h3>Change History</h3>{history?.length ? history.slice(0, 5).map((item) => <p key={item.id}>{item.action} · {item.changed_by_name || 'System'} · {new Date(item.changed_at).toLocaleString()}</p>) : <p>No history available.</p>}</section><div className="modal-actions offer-icon-actions"><ActionIcon title="Edit" icon="edit" tone="edit" onClick={onEdit} />{canDelete ? <ActionIcon title="Delete" icon="trash" tone="delete" onClick={() => onDelete(entry)} /> : null}{entry.listing_url ? <ActionIcon title="Open eBay Listing" icon="external" tone="external" href={entry.listing_url} external /> : null}{entry.related_conversation_id ? <ActionIcon title="Open Related Conversation" icon="message" tone="conversation" href={`/inbox?conversation_id=${entry.related_conversation_id}`} /> : null}</div></aside></div>
}

export default function OfferManagement({ currentUser, onLogout }) {
  const isAgent = normalizeRole(currentUser?.role) === 'AGENT'
  const canDelete = !isAgent

  const defaultFilters = {
    page: 1,
    page_size: 25,
    sort_by: 'updated_at',
    sort_order: 'desc',
    from_date: todayDateValue(),
    to_date: todayDateValue(),
  }

  const [filters, setFilters] = useState(defaultFilters)

  const [data, setData] = useState({
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
  })

  const [summary, setSummary] = useState({})

  const [lookups, setLookups] = useState({
    statuses: [],
    outcomes: [],
    currencies: [],
  })

  const [accounts, setAccounts] = useState([])
  const [users, setUsers] = useState([])
  const [modalEntry, setModalEntry] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [selectedEntryIds, setSelectedEntryIds] = useState(
    () => new Set(),
  )
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const importInputRef = useRef(null)

  const activeFilters = useMemo(
    () => ({
      ...filters,
      page: undefined,
      page_size: undefined,
      sort_by: undefined,
      sort_order: undefined,
    }),
    [filters],
  )

  async function load(nextFilters = filters) {
    try {
      const summaryFilters = {
        ...nextFilters,
        page: undefined,
        page_size: undefined,
        sort_by: undefined,
        sort_order: undefined,
      }

      const [list, counts] = await Promise.all([
        fetchOfferEntries(nextFilters),
        fetchOfferSummary(summaryFilters),
      ])

      setData(list)
      setSummary(counts)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load offers.')
    }
  }

  useEffect(() => {
    let isMounted = true

    Promise.allSettled([
      fetchOfferLookups(),
      fetchEbayAccounts(),
      isAgent ? Promise.resolve({ items: [] }) : fetchUsers(),
    ]).then(([lookupsResult, accountsResult, usersResult]) => {
      if (!isMounted) {
        return
      }

      if (lookupsResult.status === 'fulfilled') {
        setLookups({
          statuses: lookupsResult.value?.statuses || [],
          outcomes: lookupsResult.value?.outcomes || [],
          currencies: lookupsResult.value?.currencies || [],
        })
      }

      if (accountsResult.status === 'fulfilled') {
        setAccounts(
          accountsResult.value?.items || accountsResult.value || [],
        )
      }

      if (usersResult.status === 'fulfilled') {
        setUsers(usersResult.value?.items || usersResult.value || [])
      }
    })

    return () => {
      isMounted = false
    }
  }, [isAgent])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      load(filters)
    }, 300)

    return () => {
      window.clearTimeout(timer)
    }
  }, [filters])

  function updateFilter(key, value) {
    setFilters((current) => ({
      ...current,
      [key]: value,
      page: 1,
    }))
  }

  function clearFilters() {
    setFilters({
      page: 1,
      page_size: 25,
      sort_by: 'updated_at',
      sort_order: 'desc',
      from_date: todayDateValue(),
      to_date: todayDateValue(),
    })
  }

  async function download() {
    try {
      const blob = await exportOfferEntries(activeFilters)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')

      link.href = url
      link.download = `offer-entries_${new Date()
        .toISOString()
        .slice(0, 10)}.xlsx`

      document.body.appendChild(link)
      link.click()
      link.remove()

      URL.revokeObjectURL(url)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to export offer entries.',
      )
    }
  }

  async function uploadExcel(event) {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) {
      return
    }

    setImporting(true)
    setImportResult(null)
    setError('')

    try {
      const result = await importOfferEntriesExcel(file)
      setImportResult(result)
      await load({
        ...filters,
        page: 1,
        sort_by: 'entry_number',
        sort_order: 'asc',
      })
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to import offer entries.',
      )
    } finally {
      setImporting(false)
    }
  }

  async function preview(entry) {
    setSelected(entry)

    try {
      const entryHistory = isAgent
        ? []
        : await fetchOfferHistory(entry.id)

      setHistory(entryHistory)
    } catch {
      setHistory([])
    }
  }

  function afterSave(saved, previewSaved = false) {
    setShowCreate(false)
    setModalEntry(null)
    load()

    if (previewSaved) {
      preview(saved)
    }
  }

  function toggleEntrySelection(entryId) {
    setSelectedEntryIds((current) => {
      const next = new Set(current)

      if (next.has(entryId)) {
        next.delete(entryId)
      } else {
        next.add(entryId)
      }

      return next
    })
  }

  function toggleSelectAllVisible(checked) {
    setSelectedEntryIds((current) => {
      const next = new Set(current)

      data.items.forEach((entry) => {
        if (checked) {
          next.add(entry.id)
        } else {
          next.delete(entry.id)
        }
      })

      return next
    })
  }

  async function confirmDelete() {
    if (!deleteTarget) {
      return
    }

    const targetId = deleteTarget.id

    try {
      await deleteOfferEntry(targetId)

      setDeleteTarget(null)
      setSelectedEntryIds((current) => {
        const next = new Set(current)
        next.delete(targetId)
        return next
      })

      if (selected?.id === targetId) {
        setSelected(null)
        setHistory([])
      }

      await load()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to delete offer entry.',
      )

      setDeleteTarget(null)
    }
  }

  async function confirmBulkDelete() {
    const entryIds = Array.from(selectedEntryIds)

    if (!entryIds.length) {
      return
    }

    setIsBulkDeleting(true)

    try {
      await bulkDeleteOfferEntries(entryIds)

      setSelectedEntryIds(new Set())

      if (selected && entryIds.includes(selected.id)) {
        setSelected(null)
        setHistory([])
      }

      await load()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to delete selected offer entries.',
      )
    } finally {
      setIsBulkDeleting(false)
    }
  }

  const allVisibleEntriesSelected =
    data.items.length > 0 &&
    data.items.every((entry) => selectedEntryIds.has(entry.id))

  const totalPages = Math.max(
    1,
    Math.ceil((data.total || 0) / (filters.page_size || 25)),
  )
  const firstVisibleEntry = data.total
    ? (filters.page - 1) * filters.page_size + 1
    : 0
  const lastVisibleEntry = data.total
    ? Math.min(filters.page * filters.page_size, data.total)
    : 0

  const statItems = [
    ['Total Entries', summary.total_entries],
    ['Open Offers', summary.open_offers],
    ['Follow-ups Due', summary.follow_ups_due],
    ['Awaiting Payment', summary.awaiting_payment],
    ['Sold', summary.sold],
    ['High-Value Offers', summary.high_value_offers],
  ]

  const textFilters = [
    ['from_date', 'From', 'date'],
    ['to_date', 'To', 'date'],
    ['buyer_id', 'Buyer ID', 'text'],
    ['sku', 'SKU', 'text'],
    ['listing_id', 'Listing ID', 'text'],
    ['search', 'Search', 'search'],
  ]

  const tableHeaders = [
    'Entry #',
    'Date',
    ...(!isAgent ? ['Agent'] : []),
    'Account',
    'Listing ID',
    'SKU',
    'Product',
    'Buyer',
    'Listed Price',
    'Buyer Offer',
    'Offered Price',
    'Best/Counteroffer',
    'Quantity',
    'Status',
    'Follow-up',
    'High Value',
    'Updated At',
    'Actions',
  ]

  return (
    <AppLayout
      activePage="Offer Management"
      currentUser={currentUser}
      onLogout={onLogout}
    >
      <main className="management-page offer-management-page">
        <div className="page-header">
          <div>
            <h1>Offer Management</h1>
            <p>Track, follow up and manage eBay offers</p>
          </div>

          <div className="page-header-actions">
            <input
              ref={importInputRef}
              className="offer-import-input"
              type="file"
              accept=".xlsx,.xls"
              onChange={uploadExcel}
            />

            <button
              className="secondary-button compact-action action-button action-import"
              type="button"
              disabled={importing}
              onClick={() => importInputRef.current?.click()}
            >
              {importing ? 'Importing...' : 'Import Excel'}
            </button>

            <button
              className="primary-button compact-action action-button action-create"
              type="button"
              onClick={() => setShowCreate(true)}
            >
              New Offer Entry
            </button>

            <button
              className="secondary-button compact-action action-button action-export"
              type="button"
              onClick={download}
            >
              Export Excel
            </button>
          </div>
        </div>

        {error ? (
          <p className="form-message error">{error}</p>
        ) : null}

        {importResult ? (
          <p className={`form-message ${importResult.error_count ? 'warning' : 'success'}`}>
            Imported {importResult.created_count} offer entries. Skipped {importResult.skipped_count}.
            {importResult.error_count ? ` ${importResult.error_count} rows need review.` : ''}
          </p>
        ) : null}

        <section className="stats-grid">
          {statItems.map(([title, value]) => (
            <article className="stat-card" key={title}>
              <div>
                <p>{title}</p>
                <strong>{value ?? 0}</strong>
              </div>
            </article>
          ))}
        </section>

        <form
          className="analytics-filter-bar offer-filter-bar"
          onSubmit={(event) => event.preventDefault()}
        >
          {textFilters.map(([key, title, type]) => (
            <label className="field" key={key}>
              <span>{title}</span>

              <input
                type={type}
                value={filters[key] || ''}
                onChange={(event) =>
                  updateFilter(key, event.target.value)
                }
              />
            </label>
          ))}

          {!isAgent ? (
            <label className="field">
              <span>Agent</span>

              <select
                value={filters.created_by_user_id || ''}
                onChange={(event) =>
                  updateFilter(
                    'created_by_user_id',
                    event.target.value,
                  )
                }
              >
                <option value="">All</option>

                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name || user.email}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="field">
            <span>Account</span>

            <select
              value={filters.ebay_account_id || ''}
              onChange={(event) =>
                updateFilter('ebay_account_id', event.target.value)
              }
            >
              <option value="">All</option>

              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_name ||
                    account.store_name ||
                    account.ebay_username}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Status</span>

            <select
              value={filters.status || ''}
              onChange={(event) =>
                updateFilter('status', event.target.value)
              }
            >
              <option value="">All</option>

              {OFFER_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {label(item)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Outcome</span>

            <select
              value={filters.outcome || ''}
              onChange={(event) =>
                updateFilter('outcome', event.target.value)
              }
            >
              <option value="">All</option>

              <option value="PENDING">Pending</option>

              {OFFER_OUTCOMES.map((item) => (
                <option key={item} value={item}>
                  {label(item)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>High Value</span>

            <select
              value={filters.is_high_value ?? ''}
              onChange={(event) =>
                updateFilter('is_high_value', event.target.value)
              }
            >
              <option value="">All</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>

          <button
            className="secondary-button compact-action"
            type="button"
            onClick={() =>
              updateFilter('next_offer_followup', todayDateValue())
            }
          >
            Today&apos;s offer followup
          </button>

          <button
            className="secondary-button compact-action"
            type="button"
            onClick={clearFilters}
          >
            Clear filters
          </button>
        </form>

        {canDelete ? (
          <section className="offer-bulk-bar">
            {selectedEntryIds.size > 0 ? (
              <>
                <strong>{selectedEntryIds.size} selected</strong>

                <button
                  className="secondary-button compact-action"
                  type="button"
                  disabled={isBulkDeleting}
                  onClick={confirmBulkDelete}
                >
                  {isBulkDeleting
                    ? 'Deleting...'
                    : 'Delete selected'}
                </button>

                <button
                  className="secondary-button compact-action"
                  type="button"
                  disabled={isBulkDeleting}
                  onClick={() => setSelectedEntryIds(new Set())}
                >
                  Clear selection
                </button>
              </>
            ) : (
              <span>Select entries to bulk delete.</span>
            )}
          </section>
        ) : null}

        <section className="table-card offer-table-card">
          <div
            className="table-scroll offer-table-scroll"
            tabIndex={0}
            aria-label="Offer entries table. Scroll horizontally to view all columns."
          >
            <table className="users-table offer-table">
              <thead>
                <tr>
                  {canDelete ? (
                    <th>
                      <input
                        type="checkbox"
                        aria-label="Select all visible entries"
                        checked={allVisibleEntriesSelected}
                        onChange={(event) =>
                          toggleSelectAllVisible(
                            event.target.checked,
                          )
                        }
                      />
                    </th>
                  ) : null}

                  {tableHeaders.map((head) => (
                    <th key={head}>{head}</th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {data.items.length > 0 ? (
                  data.items.map((entry) => (
                    <tr key={entry.id}>
                      {canDelete ? (
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Select entry #${entry.entry_number}`}
                            checked={selectedEntryIds.has(entry.id)}
                            onChange={() =>
                              toggleEntrySelection(entry.id)
                            }
                          />
                        </td>
                      ) : null}

                      <td>#{entry.entry_number}</td>
                      <td>{entry.offer_date || '—'}</td>

                      {!isAgent ? (
                        <td>{entry.agent_name || '—'}</td>
                      ) : null}

                      <td>{entry.ebay_account_name || '—'}</td>
                      <td>{entry.listing_id || '—'}</td>
                      <td>{entry.sku || '—'}</td>

                      <td
                        className="truncate-cell"
                        title={entry.product_title || ''}
                      >
                        {entry.product_title || '—'}
                      </td>

                      <td>{entry.buyer_id || '—'}</td>

                      <td>
                        {money(
                          entry.listed_price,
                          entry.currency,
                        )}
                      </td>

                      <td>
                        {money(
                          entry.buyer_offer_price,
                          entry.currency,
                        )}
                      </td>

                      <td>{entry.offered_price || '—'}</td>

                      <td>
                        {money(
                          entry.counteroffer_price,
                          entry.currency,
                        )}
                      </td>

                      <td>
                        {entry.offer_quantity ??
                          entry.listing_quantity ??
                          '—'}
                      </td>

                      <td>
                        <Badge value={entry.status} />
                      </td>

                      <td>
                        {entry.next_offer_followup
                          ? entry.next_offer_followup
                          : '—'}
                      </td>

                      <td>
                        {entry.is_high_value ? (
                          <Badge value="Yes" tone="active" />
                        ) : (
                          '—'
                        )}
                      </td>

                      <td>
                        {entry.updated_at
                          ? new Date(
                              entry.updated_at,
                            ).toLocaleString()
                          : '—'}
                      </td>

                      <td>
                        <div className="offer-icon-actions">
                          <ActionIcon
                            title="Preview"
                            icon="eye"
                            tone="preview"
                            onClick={() => preview(entry)}
                          />

                          <ActionIcon
                            title="Edit"
                            icon="edit"
                            tone="edit"
                            onClick={() => setModalEntry(entry)}
                          />

                          {canDelete ? (
                            <ActionIcon
                              title="Delete"
                              icon="trash"
                              tone="delete"
                              onClick={() =>
                                setDeleteTarget(entry)
                              }
                            />
                          ) : null}

                          {entry.listing_url ? (
                            <ActionIcon
                              title="Open eBay Listing"
                              icon="external"
                              tone="external"
                              href={entry.listing_url}
                              external
                            />
                          ) : null}

                          {entry.related_conversation_id ? (
                            <ActionIcon
                              title="Open Related Conversation"
                              icon="message"
                              tone="conversation"
                              href={`/inbox?conversation_id=${entry.related_conversation_id}`}
                            />
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      className="empty-table-message"
                      colSpan={
                        tableHeaders.length + (canDelete ? 1 : 0)
                      }
                    >
                      No offer entries found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar offer-pagination-bar">
            <span>
              Showing {firstVisibleEntry}-{lastVisibleEntry} of {data.total || 0}
            </span>

            <div>
              <button
                className="pagination-button"
                type="button"
                disabled={filters.page <= 1}
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    page: Math.max(1, current.page - 1),
                  }))
                }
              >
                Prev
              </button>

              <span className="offer-pagination-page">
                Page {filters.page} of {totalPages}
              </span>

              <button
                className="pagination-button"
                type="button"
                disabled={filters.page >= totalPages}
                onClick={() =>
                  setFilters((current) => ({
                    ...current,
                    page: Math.min(totalPages, current.page + 1),
                  }))
                }
              >
                Next
              </button>

              <select
                value={filters.page_size}
                aria-label="Offer entries per page"
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    page: 1,
                    page_size: Number(event.target.value),
                  }))
                }
              >
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="200">200</option>
              </select>
            </div>
          </div>
        </section>
      </main>

      {/* CREATE OFFER */}
      {showCreate ? (
        <OfferForm
          entry={null}
          lookups={lookups}
          accounts={accounts}
          onCancel={() => setShowCreate(false)}
          onSaved={afterSave}
        />
      ) : null}

      {/* EDIT OFFER */}
      {modalEntry ? (
        <OfferForm
          entry={modalEntry}
          lookups={lookups}
          accounts={accounts}
          onCancel={() => setModalEntry(null)}
          onSaved={afterSave}
        />
      ) : null}

      {/* PREVIEW OFFER */}
      {selected ? (
        <PreviewDrawer
          entry={selected}
          history={history}
          canDelete={canDelete}
          onClose={() => {
            setSelected(null)
            setHistory([])
          }}
          onEdit={() => {
            setModalEntry(selected)
            setSelected(null)
          }}
          onDelete={(entry) => {
            setSelected(null)
            setDeleteTarget(entry)
          }}
        />
      ) : null}

      {/* DELETE CONFIRMATION */}
      {deleteTarget ? (
        <div className="modal-backdrop" role="presentation">
          <section
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-offer-title"
          >
            <div className="modal-header">
              <h2 id="delete-offer-title">
                Delete Offer Entry
              </h2>

              <button
                className="icon-button"
                type="button"
                onClick={() => setDeleteTarget(null)}
              >
                <Icon name="close" />
              </button>
            </div>

            <div className="management-form">
              <p>
                Are you sure you want to delete offer entry
                {deleteTarget.entry_number
                  ? ` #${deleteTarget.entry_number}`
                  : ''}
                ?
              </p>

              <p>This action cannot be undone.</p>

              <div className="modal-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                >
                  Cancel
                </button>

                <button
                  className="primary-button"
                  type="button"
                  onClick={confirmDelete}
                >
                  Delete Entry
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {importing ? (
        <div className="offer-import-overlay" role="status" aria-live="polite">
          <div className="offer-import-panel">
            <div className="offer-import-spinner" />
            <h2>Importing Excel</h2>
            <p>Reading the sheet, validating essential fields, and saving offers.</p>
          </div>
        </div>
      ) : null}

    </AppLayout>
  )
}

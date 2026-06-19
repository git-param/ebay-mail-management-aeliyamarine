import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import {
  activateEbayAccount,
  connectEbayAccount,
  createEbayAccount,
  deactivateEbayAccount,
  deleteEbayAccount,
  fetchEbayAccount,
  fetchEbayAccounts,
  syncAllEbayAccounts,
  syncEbayAccount,
  updateEbayAccount,
} from '../services/ebayAccountApi'
import { normalizeRole } from '../utils/roles'

const ENVIRONMENTS = ['SANDBOX', 'PRODUCTION']
const CONNECTION_STATUSES = ['CONNECTED', 'PENDING', 'DISCONNECTED', 'EXPIRED', 'FAILED']

const EMPTY_FORM = {
  accountName: '',
  ebayUsername: '',
  environment: 'SANDBOX',
  notes: '',
}

function formatDate(value) {
  if (!value) {
    return 'Not synced'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatLabel(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function normalizeAccount(account) {
  return {
    ...account,
    id: account.id,
    accountName: account.account_name || '',
    ebayUsername: account.ebay_username || '',
    storeName: account.store_name || '',
    environment: account.environment || 'SANDBOX',
    connectionStatus: account.connection_status || 'DISCONNECTED',
    status: account.is_active ? 'Active' : 'Inactive',
    isActive: Boolean(account.is_active),
    lastSync: formatDate(account.last_sync_at),
    createdDate: formatDate(account.created_at),
    updatedDate: formatDate(account.updated_at),
    notes: account.notes || '',
    syncStatus: account.sync_status || 'Not synced',
    raw: account,
  }
}

function normalizeSyncResult(result) {
  const messagesProcessed = (result.messages_created || 0) + (result.messages_updated || 0)
  return {
    accountId: result.account_id,
    ebayUsername: result.ebay_username,
    status: result.status,
    conversationsProcessed: result.conversations_processed || 0,
    conversationsFailed: result.conversations_failed || 0,
    failedConversationIds: result.failed_conversation_ids || [],
    messagesProcessed,
    elapsedSeconds: result.elapsed_seconds,
    errorMessage: result.error_message || '',
  }
}

function formatElapsed(value) {
  if (!Number.isFinite(Number(value))) {
    return 'Not available'
  }

  return `${Number(value).toFixed(2)}s`
}

function getAccountsFromResponse(response) {
  if (Array.isArray(response)) {
    return response
  }

  if (Array.isArray(response.data)) {
    return response.data
  }

  return response.accounts || response.items || []
}

function toAccountPayload(values) {
  return {
    account_name: values.accountName.trim(),
    ebay_username: values.ebayUsername.trim(),
    environment: values.environment,
    notes: values.notes.trim() || null,
  }
}

function StatCard({ label, value }) {
  return (
    <article className="stat-card">
      <span className="stat-icon">
        <Icon name="bag" />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  )
}

function Badge({ type, value }) {
  const className = `${type}-badge ${type}-${String(value).toLowerCase().replace(/[\s_]+/g, '-')}`
  return <span className={className}>{formatLabel(value)}</span>
}

function Modal({ title, children, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-header">
          <h2 id="modal-title">{title}</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
            x
          </button>
        </div>
        {children}
      </section>
    </div>
  )
}

function AccountForm({ initialValues, isSubmitting, submitLabel, onCancel, onSubmit }) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})

  function updateField(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = {}

    if (!values.accountName.trim()) {
      nextErrors.accountName = 'Account name is required.'
    }
    if (!values.ebayUsername.trim()) {
      nextErrors.ebayUsername = 'eBay username is required.'
    }

    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      return
    }

    onSubmit(values)
  }

  return (
    <form className="management-form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Account Name</span>
        <input name="accountName" value={values.accountName} onChange={updateField} />
        {errors.accountName ? <small>{errors.accountName}</small> : null}
      </label>

      <label className="field">
        <span>eBay Username</span>
        <input name="ebayUsername" value={values.ebayUsername} onChange={updateField} />
        {errors.ebayUsername ? <small>{errors.ebayUsername}</small> : null}
      </label>

      <label className="field">
        <span>Environment</span>
        <select name="environment" value={values.environment} onChange={updateField}>
          {ENVIRONMENTS.map((environment) => (
            <option value={environment} key={environment}>
              {formatLabel(environment)}
            </option>
          ))}
        </select>
      </label>

      <label className="field form-field-wide">
        <span>Notes</span>
        <textarea name="notes" value={values.notes} onChange={updateField} rows="4" />
      </label>

      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="primary-button compact" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : submitLabel}
        </button>
      </div>
    </form>
  )
}

function ConfirmModal({ title, message, actionLabel, danger, isSubmitting, onCancel, onConfirm }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="confirm-message">{message}</p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button
          className={danger ? 'danger-button' : 'primary-button compact'}
          type="button"
          onClick={onConfirm}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Working...' : actionLabel}
        </button>
      </div>
    </Modal>
  )
}

function SyncSummary({ results }) {
  if (!results.length) {
    return null
  }

  const totals = results.reduce(
    (summary, result) => ({
      conversations: summary.conversations + result.conversationsProcessed,
      messages: summary.messages + result.messagesProcessed,
      failed: summary.failed + result.conversationsFailed,
      elapsed: summary.elapsed + (Number(result.elapsedSeconds) || 0),
    }),
    { conversations: 0, messages: 0, failed: 0, elapsed: 0 },
  )

  return (
    <section className="sync-summary" aria-label="Sync summary">
      <strong>Last sync</strong>
      <span>{results.length} account{results.length === 1 ? '' : 's'}</span>
      <span>{totals.conversations} conversations</span>
      <span>{totals.failed} failed</span>
      <span>{totals.messages} messages</span>
      <span>{formatElapsed(totals.elapsed)}</span>
    </section>
  )
}

function AccountDrawer({ account, onClose }) {
  if (!account) {
    return null
  }

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="user-drawer" aria-labelledby="drawer-title">
        <div className="drawer-header">
          <h2 id="drawer-title">Account Details</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
            x
          </button>
        </div>

        <div className="drawer-profile">
          <span className="avatar large">EB</span>
          <h3>{account.accountName}</h3>
          <p>{account.ebayUsername}</p>
          <div className="badge-row">
            <Badge type="environment" value={account.environment} />
            <Badge type="connection" value={account.connectionStatus} />
            <Badge type="status" value={account.status} />
          </div>
        </div>

        <dl className="detail-grid">
          <div>
            <dt>Last Sync</dt>
            <dd>{account.lastSync}</dd>
          </div>
          <div>
            <dt>Created Date</dt>
            <dd>{account.createdDate}</dd>
          </div>
          <div>
            <dt>Updated Date</dt>
            <dd>{account.updatedDate}</dd>
          </div>
          <div>
            <dt>Sync Status</dt>
            <dd>{account.syncStatus}</dd>
          </div>
        </dl>

        <section className="drawer-section">
          <h3>Notes</h3>
          <p className="drawer-note">{account.notes || 'No notes added.'}</p>
        </section>
      </aside>
    </div>
  )
}

function EbayAccounts({ currentUser, onLogout }) {
  const [accounts, setAccounts] = useState([])
  const [selectedAccountIds, setSelectedAccountIds] = useState(() => new Set())
  const [search, setSearch] = useState('')
  const [environmentFilter, setEnvironmentFilter] = useState('All Environments')
  const [statusFilter, setStatusFilter] = useState('All Statuses')
  const [actionAccountId, setActionAccountId] = useState(null)
  const [selectedAccount, setSelectedAccount] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')
  const [error, setError] = useState('')
  const [syncResults, setSyncResults] = useState([])
  const [connectingAccountId, setConnectingAccountId] = useState('')
  const [syncingAction, setSyncingAction] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const isAdmin = normalizeRole(currentUser?.role) === 'ADMIN'

  async function loadAccounts() {
    setIsLoading(true)
    setError('')

    try {
      const response = await fetchEbayAccounts()
      setAccounts(getAccountsFromResponse(response).map(normalizeAccount))
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAccounts()
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connectionStatus = params.get('ebay_connection')
    if (!connectionStatus) {
      return
    }

    if (connectionStatus === 'success') {
      showNotification('eBay account connected successfully.')
    } else {
      setError(params.get('message') || 'eBay authorization failed. Please try again.')
    }

    loadAccounts()
    window.history.replaceState({}, document.title, window.location.pathname)
  }, [])

  const filteredAccounts = useMemo(() => {
    return accounts.filter((account) => {
      const query = search.trim().toLowerCase()
      const matchesSearch =
        !query ||
        account.accountName.toLowerCase().includes(query) ||
        account.ebayUsername.toLowerCase().includes(query)
      const matchesEnvironment = environmentFilter === 'All Environments' || account.environment === environmentFilter
      const matchesStatus = statusFilter === 'All Statuses' || account.connectionStatus === statusFilter
      return matchesSearch && matchesEnvironment && matchesStatus
    })
  }, [accounts, environmentFilter, search, statusFilter])

  const stats = useMemo(
    () => ({
      total: accounts.length,
      active: accounts.filter((account) => account.isActive).length,
      connected: accounts.filter((account) => account.connectionStatus === 'CONNECTED').length,
      lastSync: accounts.find((account) => account.syncStatus !== 'Not synced')?.syncStatus || 'Not synced',
    }),
    [accounts],
  )

  const connectedAccounts = useMemo(
    () => accounts.filter((account) => account.connectionStatus === 'CONNECTED'),
    [accounts],
  )

  const selectedConnectedAccountIds = useMemo(
    () => connectedAccounts.filter((account) => selectedAccountIds.has(account.id)).map((account) => account.id),
    [connectedAccounts, selectedAccountIds],
  )

  function showNotification(message) {
    setNotification(message)
    window.setTimeout(() => setNotification(''), 2800)
  }

  function showError(caughtError) {
    const message = caughtError.message || 'Something went wrong. Please try again.'
    setError(message)
    showNotification(message)
  }

  function openModal(type, account = null) {
    setActionAccountId(null)
    setSelectedAccount(account)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedAccount(null)
  }

  async function createAccount(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await createEbayAccount(toAccountPayload(values))
      closeModal()
      showNotification('eBay account created successfully.')
      await loadAccounts()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function updateAccount(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await updateEbayAccount(selectedAccount.id, toAccountPayload(values))
      closeModal()
      showNotification('eBay account updated successfully.')
      await loadAccounts()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function setAccountActive(account, isActive) {
    setIsSubmitting(true)
    setError('')

    try {
      if (isActive) {
        await activateEbayAccount(account.id)
      } else {
        await deactivateEbayAccount(account.id)
      }
      closeModal()
      showNotification(isActive ? 'eBay account activated successfully.' : 'eBay account deactivated successfully.')
      await loadAccounts()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function removeAccount() {
    setIsSubmitting(true)
    setError('')

    try {
      await deleteEbayAccount(selectedAccount.id)
      closeModal()
      showNotification('eBay account deleted successfully.')
      await loadAccounts()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function viewAccount(account) {
    setActionAccountId(null)
    setError('')

    try {
      const response = await fetchEbayAccount(account.id)
      setSelectedAccount(normalizeAccount(response))
    } catch (caughtError) {
      showError(caughtError)
    }
  }

  function toggleAccountSelection(accountId) {
    setSelectedAccountIds((current) => {
      const next = new Set(current)
      if (next.has(accountId)) {
        next.delete(accountId)
      } else {
        next.add(accountId)
      }
      return next
    })
  }

  async function connectAccount(account) {
    setConnectingAccountId(account.id)
    setError('')

    try {
      const response = await connectEbayAccount(account.id)
      showNotification('Opening eBay authorization...')
      window.location.assign(response.authorization_url)
    } catch (caughtError) {
      showError(caughtError)
      setConnectingAccountId('')
    }
  }

  async function runSync(label, syncRequest) {
    setSyncingAction(label)
    setError('')
    setSyncResults([])

    try {
      const response = await syncRequest()
      const results = Array.isArray(response.results)
        ? response.results.map(normalizeSyncResult)
        : [normalizeSyncResult(response)]
      setSyncResults(results)
      showNotification('Sync completed successfully.')
      await loadAccounts()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setSyncingAction('')
    }
  }

  async function syncSingleAccount(account) {
    await runSync(account.id, () => syncEbayAccount(account.id))
  }

  async function syncSelectedAccounts() {
    const accountIds = selectedConnectedAccountIds
    if (!accountIds.length) {
      return
    }

    await runSync('selected', async () => ({
      results: await Promise.all(accountIds.map((accountId) => syncEbayAccount(accountId))),
    }))
  }

  async function syncAllConnectedAccounts() {
    await runSync('all', syncAllEbayAccounts)
  }

  function resetFilters() {
    setSearch('')
    setEnvironmentFilter('All Environments')
    setStatusFilter('All Statuses')
  }

  return (
    <AppLayout activePage="eBay Accounts" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>eBay Accounts</h1>
            <p>Manage connected eBay seller accounts</p>
          </div>
          <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
            <Icon name="plus" />
            Add Account
          </button>
        </div>

        <section className="stats-grid" aria-label="eBay account summary">
          <StatCard label="Total Accounts" value={stats.total} />
          <StatCard label="Active Accounts" value={stats.active} />
          <StatCard label="Connected Accounts" value={stats.connected} />
          <StatCard label="Last Sync Status" value={stats.lastSync} />
        </section>

        {isAdmin ? (
          <section className="sync-controls" aria-label="eBay sync controls">
            <button
              className="secondary-button"
              type="button"
              disabled={!selectedConnectedAccountIds.length || Boolean(syncingAction)}
              onClick={syncSelectedAccounts}
            >
              {syncingAction === 'selected' ? 'Syncing...' : `Sync Selected (${selectedConnectedAccountIds.length})`}
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!connectedAccounts.length || Boolean(syncingAction)}
              onClick={syncAllConnectedAccounts}
            >
              {syncingAction === 'all' ? 'Syncing...' : 'Sync All Connected'}
            </button>
          </section>
        ) : null}

        <SyncSummary results={syncResults} />

        <section className="filter-panel" aria-label="eBay account filters">
          <label className="field search-field">
            <span>Search</span>
            <input
              type="search"
              placeholder="Search by account or username"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Environment</span>
            <select value={environmentFilter} onChange={(event) => setEnvironmentFilter(event.target.value)}>
              <option>All Environments</option>
              {ENVIRONMENTS.map((environment) => (
                <option value={environment} key={environment}>
                  {formatLabel(environment)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option>All Statuses</option>
              {CONNECTION_STATUSES.map((status) => (
                <option value={status} key={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </label>

          <button className="secondary-button" type="button" onClick={resetFilters}>
            Reset Filters
          </button>
        </section>

        {error ? (
          <p className="form-message error management-error" role="alert">
            {error}
          </p>
        ) : null}

        <section className="table-card" aria-label="eBay accounts table">
          {isLoading ? (
            <div className="empty-state">
              <h2>Loading eBay accounts...</h2>
            </div>
          ) : filteredAccounts.length ? (
            <div className="table-scroll">
              <table className="users-table">
                <thead>
                  <tr>
                    {isAdmin ? <th>Select</th> : null}
                    <th>Account Name</th>
                    <th>eBay Username</th>
                    <th>Environment</th>
                    <th>Connection Status</th>
                    <th>Last Sync</th>
                    <th>Created Date</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAccounts.map((account) => (
                    <tr key={account.id}>
                      {isAdmin ? (
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedAccountIds.has(account.id)}
                            disabled={account.connectionStatus !== 'CONNECTED' || Boolean(syncingAction)}
                            onChange={() => toggleAccountSelection(account.id)}
                            aria-label={`Select ${account.accountName}`}
                          />
                        </td>
                      ) : null}
                      <td>
                        <strong>{account.accountName}</strong>
                      </td>
                      <td>{account.ebayUsername}</td>
                      <td>
                        <Badge type="environment" value={account.environment} />
                      </td>
                      <td>
                        <Badge type="connection" value={account.connectionStatus} />
                      </td>
                      <td>{account.lastSync}</td>
                      <td>{account.createdDate}</td>
                      <td>
                        <Badge type="status" value={account.status} />
                      </td>
                      <td className="actions-cell">
                        {account.connectionStatus !== 'CONNECTED' ? (
                          <button
                            className="secondary-button compact-action"
                            type="button"
                            onClick={() => connectAccount(account)}
                            disabled={connectingAccountId === account.id}
                          >
                            {connectingAccountId === account.id ? 'Connecting...' : 'Connect'}
                          </button>
                        ) : null}
                        {isAdmin && account.connectionStatus === 'CONNECTED' ? (
                          <button
                            className="secondary-button compact-action"
                            type="button"
                            onClick={() => syncSingleAccount(account)}
                            disabled={Boolean(syncingAction)}
                          >
                            {syncingAction === account.id ? 'Syncing...' : 'Sync'}
                          </button>
                        ) : null}
                        <button
                          className="icon-button"
                          type="button"
                          onClick={() =>
                            setActionAccountId((current) => (current === account.id ? null : account.id))
                          }
                          aria-label={`Open actions for ${account.accountName}`}
                        >
                          <Icon name="dots" />
                        </button>
                        {actionAccountId === account.id ? (
                          <div className="action-menu">
                            <button className="menu-view" type="button" onClick={() => viewAccount(account)}>
                              <Icon name="eye" />
                              View
                            </button>
                            <button className="menu-edit" type="button" onClick={() => openModal('edit', account)}>
                              <Icon name="edit" />
                              Edit
                            </button>
                            {account.isActive ? (
                              <button
                                className="menu-disable"
                                type="button"
                                onClick={() => openModal('deactivate', account)}
                                disabled={isSubmitting}
                              >
                                <Icon name="disable" />
                                Deactivate
                              </button>
                            ) : (
                              <button
                                className="menu-activate"
                                type="button"
                                onClick={() => setAccountActive(account, true)}
                                disabled={isSubmitting}
                              >
                                <Icon name="activate" />
                                Activate
                              </button>
                            )}
                            <button className="menu-disable" type="button" onClick={() => openModal('delete', account)}>
                              <Icon name="disable" />
                              Delete
                            </button>
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <h2>No eBay accounts found</h2>
              <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
                Add Account
              </button>
            </div>
          )}
        </section>
      </main>

      {notification ? <div className="toast">{notification}</div> : null}

      {modal === 'create' ? (
        <Modal title="Add Account" onClose={closeModal}>
          <AccountForm
            initialValues={EMPTY_FORM}
            isSubmitting={isSubmitting}
            submitLabel="Create"
            onCancel={closeModal}
            onSubmit={createAccount}
          />
        </Modal>
      ) : null}

      {modal === 'edit' && selectedAccount ? (
        <Modal title="Edit Account" onClose={closeModal}>
          <AccountForm
            initialValues={{
              accountName: selectedAccount.accountName,
              ebayUsername: selectedAccount.ebayUsername,
              environment: selectedAccount.environment,
              notes: selectedAccount.notes,
            }}
            isSubmitting={isSubmitting}
            submitLabel="Save Changes"
            onCancel={closeModal}
            onSubmit={updateAccount}
          />
        </Modal>
      ) : null}

      {modal === 'deactivate' && selectedAccount ? (
        <ConfirmModal
          title="Deactivate Account"
          message={`Deactivate ${selectedAccount.accountName}? Syncs and future account activity will be paused.`}
          actionLabel="Deactivate"
          danger
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={() => setAccountActive(selectedAccount, false)}
        />
      ) : null}

      {modal === 'delete' && selectedAccount ? (
        <ConfirmModal
          title="Delete Account"
          message={`Delete ${selectedAccount.accountName}? This removes the account record from Omni-Desk.`}
          actionLabel="Delete"
          danger
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={removeAccount}
        />
      ) : null}

      <AccountDrawer
        account={selectedAccount && !modal ? selectedAccount : null}
        onClose={() => setSelectedAccount(null)}
      />
    </AppLayout>
  )
}

export default EbayAccounts

import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../../layouts/app_layout'
import { deleteConversationData, fetchAccountSyncStates, fetchConfigSettings, updateAccountSyncState, updateConfigSettings } from '../../services/configApi'

const SECTION_LABELS = {
  offer: 'Offer Section',
  api: 'API Section',
}

export default function Config({ currentUser, onLogout }) {
  const [settings, setSettings] = useState([])
  const [draft, setDraft] = useState({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [accounts, setAccounts] = useState([])
  const [syncForm, setSyncForm] = useState({ account_id: '', apply_to_all: false, last_sync_at: '' })
  const [isSyncSaving, setIsSyncSaving] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)

  const grouped = useMemo(() => settings.reduce((groups, setting) => {
    const section = setting.section || 'general'
    groups[section] = groups[section] || []
    groups[section].push(setting)
    return groups
  }, {}), [settings])

  async function load() {
    setError('')
    try {
      const data = await fetchConfigSettings()
      const accountData = await fetchAccountSyncStates()
      setSettings(data)
      setAccounts(accountData)
      setDraft(Object.fromEntries(data.map((setting) => [setting.config_key, setting.value])))
    } catch (caughtError) {
      setError(caughtError.message)
    }
  }

  async function save(event) {
    event.preventDefault()
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const data = await updateConfigSettings(Object.entries(draft).map(([config_key, value]) => ({ config_key, value })))
      setSettings(data)
      setDraft(Object.fromEntries(data.map((setting) => [setting.config_key, setting.value])))
      setMessage('Configuration saved.')
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsSaving(false)
    }
  }

  async function saveSyncCursor(event) {
    event.preventDefault()
    setIsSyncSaving(true)
    setError('')
    setMessage('')
    try {
      const result = await updateAccountSyncState({
        account_id: syncForm.apply_to_all ? null : syncForm.account_id || null,
        apply_to_all: syncForm.apply_to_all,
        last_sync_at: syncForm.last_sync_at ? new Date(syncForm.last_sync_at).toISOString() : null,
      })
      setMessage(`Updated sync cursor for ${result.updated_count} account${result.updated_count === 1 ? '' : 's'}.`)
      setAccounts(await fetchAccountSyncStates())
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsSyncSaving(false)
    }
  }

  async function deleteAllConversations() {
    setIsDeleting(true)
    setError('')
    setMessage('')
    try {
      const result = await deleteConversationData(deleteConfirm)
      setDeleteConfirm('')
      setMessage(`Deleted ${result.total_deleted || 0} conversation-related rows.`)
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsDeleting(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
  }, [])

  return (
    <AppLayout activePage="Config" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page config-page">
        <div className="page-header">
          <div>
            <h1>Config</h1>
            <p>Configure operational limits and module settings</p>
          </div>
          <button className="secondary-button compact-action" type="button" onClick={load}>Refresh</button>
        </div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <form className="config-sections" onSubmit={save}>
          {Object.entries(grouped).map(([section, items]) => (
            <section className="table-card config-section" key={section}>
              <div className="config-section-header">
                <h2>{SECTION_LABELS[section] || `${section} Section`}</h2>
              </div>
              <div className="config-grid">
                {items.map((setting) => (
                  <label className="field config-field" key={setting.config_key}>
                    <span>{setting.label}</span>
                    <input
                      type={setting.value_type === 'integer' || setting.value_type === 'decimal' ? 'number' : 'text'}
                      step={setting.value_type === 'decimal' ? '0.01' : '1'}
                      min="0"
                      value={draft[setting.config_key] ?? ''}
                      disabled={!setting.is_editable}
                      onChange={(event) => setDraft((current) => ({ ...current, [setting.config_key]: event.target.value }))}
                    />
                    {setting.description ? <small>{setting.description}</small> : null}
                  </label>
                ))}
              </div>
            </section>
          ))}
          <div className="modal-actions">
            <button className="primary-button" type="submit" disabled={isSaving}>{isSaving ? 'Saving...' : 'Save Config'}</button>
          </div>
        </form>
        <section className="table-card config-section">
          <div className="config-section-header">
            <h2>Account Sync Controls</h2>
          </div>
          <form className="config-grid" onSubmit={saveSyncCursor}>
            <label className="checkbox-field config-wide-field"><input type="checkbox" checked={syncForm.apply_to_all} onChange={(event) => setSyncForm((current) => ({ ...current, apply_to_all: event.target.checked }))} /> Apply to all eBay accounts</label>
            <label className="field config-field">
              <span>eBay account</span>
              <select value={syncForm.account_id} disabled={syncForm.apply_to_all} onChange={(event) => setSyncForm((current) => ({ ...current, account_id: event.target.value }))}>
                <option value="">Select account</option>
                {accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.store_name || account.ebay_username}</option>)}
              </select>
              <small>Updates both conversation and order sync cursors.</small>
            </label>
            <label className="field config-field">
              <span>Last sync timestamp</span>
              <input type="datetime-local" value={syncForm.last_sync_at} onChange={(event) => setSyncForm((current) => ({ ...current, last_sync_at: event.target.value }))} />
              <small>Leave empty to reset the cursor and force a broader sync.</small>
            </label>
            <div className="modal-actions config-inline-actions">
              <button className="primary-button" type="submit" disabled={isSyncSaving}>{isSyncSaving ? 'Updating...' : 'Update Last Sync'}</button>
            </div>
          </form>
          <div className="config-account-list">
            {accounts.map((account) => <p key={account.id}><strong>{account.account_name || account.ebay_username}</strong> Last sync: {account.last_sync_at ? new Date(account.last_sync_at).toLocaleString() : 'Not synced'} Order sync: {account.last_order_sync_at ? new Date(account.last_order_sync_at).toLocaleString() : 'Not synced'}</p>)}
          </div>
        </section>
        <section className="table-card config-section config-danger-section">
          <div className="config-section-header">
            <h2>Danger Zone</h2>
          </div>
          <p className="confirm-message">Delete all conversations, messages, assignments, notifications, offers, offer-management entries, audit logs, and synced order records from the database. eBay accounts, users, roles, categories, templates, config, and Sold Posting records are kept.</p>
          <label className="field config-field">
            <span>Type DELETE CONVERSATIONS to confirm</span>
            <input value={deleteConfirm} onChange={(event) => setDeleteConfirm(event.target.value)} />
          </label>
          <div className="modal-actions">
            <button className="danger-button" type="button" disabled={isDeleting || deleteConfirm !== 'DELETE CONVERSATIONS'} onClick={deleteAllConversations}>{isDeleting ? 'Deleting...' : 'Delete Conversation Data'}</button>
          </div>
        </section>
      </main>
    </AppLayout>
  )
}

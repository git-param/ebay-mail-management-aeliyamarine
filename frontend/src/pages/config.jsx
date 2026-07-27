import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { fetchConfigSettings, updateConfigSettings } from '../services/configApi'

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
      setSettings(data)
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

  useEffect(() => {
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
      </main>
    </AppLayout>
  )
}

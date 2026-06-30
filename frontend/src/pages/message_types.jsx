import { useEffect, useMemo, useState } from 'react'

import AppLayout from '../layouts/app_layout'
import { createMessageType, deleteMessageType, fetchMessageTypes, setMessageTypeStatus, updateMessageType } from '../services/messageTypeApi'

const EMPTY_FORM = { name: '', parent_id: '', description: '', display_order: 0, keywords: '' }

function flatten(nodes, depth = 0) {
  return nodes.flatMap((node) => [{ ...node, depth }, ...flatten(node.children || [], depth + 1)])
}

function keywordList(value) {
  return [...new Set(value.split(',').map((keyword) => keyword.trim()).filter(Boolean))]
}

export default function MessageTypes({ currentUser, onLogout }) {
  const [tree, setTree] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState('')
  const [error, setError] = useState('')
  const items = useMemo(() => flatten(tree), [tree])

  async function load() {
    try {
      setTree(await fetchMessageTypes(true))
      setError('')
    } catch (caughtError) {
      setError(caughtError.message)
    }
  }

  useEffect(() => { load() }, [])

  function edit(item) {
    setEditing(item.id)
    setForm({
      name: item.name,
      parent_id: item.parent_id || '',
      description: item.description || '',
      display_order: item.display_order,
      keywords: (item.keywords || []).join(', '),
    })
  }

  async function submit(event) {
    event.preventDefault()
    try {
      const payload = {
        ...form,
        parent_id: form.parent_id || null,
        display_order: Number(form.display_order),
        keywords: keywordList(form.keywords),
      }
      if (editing) await updateMessageType(editing, payload)
      else await createMessageType(payload)
      setForm(EMPTY_FORM)
      setEditing('')
      await load()
    } catch (caughtError) {
      setError(caughtError.message)
    }
  }

  return (
    <AppLayout activePage="Message Types" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Message Types</h1>
            <p>Manage reply classifications and keywords used for automatic pre-selection.</p>
          </div>
        </div>
        {error ? <p className="form-message error">{error}</p> : null}
        <form className="analytics-filter-bar" onSubmit={submit}>
          <label className="field"><span>Name</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          <label className="field"><span>Parent</span><select value={form.parent_id} onChange={(event) => setForm({ ...form, parent_id: event.target.value })}><option value="">Root type</option>{items.filter((item) => item.id !== editing && !item.is_deleted).map((item) => <option value={item.id} key={item.id}>{'— '.repeat(item.depth)}{item.name}</option>)}</select></label>
          <label className="field"><span>Order</span><input type="number" min="0" value={form.display_order} onChange={(event) => setForm({ ...form, display_order: event.target.value })} /></label>
          <label className="field"><span>Description</span><input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
          <label className="field form-field-wide"><span>Detection keywords</span><input value={form.keywords} onChange={(event) => setForm({ ...form, keywords: event.target.value })} placeholder="tracking, shipment, delivered, fedex" /><small>Comma-separated; matched against the latest four messages.</small></label>
          <div className="analytics-filter-actions">
            <button className="primary-button compact" type="submit">{editing ? 'Save' : 'Create'}</button>
            {editing ? <button className="secondary-button compact" type="button" onClick={() => { setEditing(''); setForm(EMPTY_FORM) }}>Cancel</button> : null}
          </div>
        </form>
        <section className="analytics-panel"><div className="report-table-wrap"><table><thead><tr><th>Name</th><th>Keywords</th><th>Status</th><th>Order</th><th>Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td style={{ paddingLeft: `${16 + item.depth * 24}px` }}>{item.name}</td><td>{(item.keywords || []).join(', ') || '—'}</td><td>{item.is_deleted ? 'Deleted' : item.is_active ? 'Active' : 'Inactive'}</td><td>{item.display_order}</td><td><button className="secondary-button compact-action" type="button" onClick={() => edit(item)}>Edit</button> {item.is_deleted ? <button className="secondary-button compact-action" type="button" onClick={async () => { await setMessageTypeStatus(item.id, { restore: true, is_active: true }); load() }}>Restore</button> : <><button className="secondary-button compact-action" type="button" onClick={async () => { await setMessageTypeStatus(item.id, { is_active: !item.is_active }); load() }}>{item.is_active ? 'Disable' : 'Enable'}</button> <button className="secondary-button compact-action" type="button" onClick={async () => { await deleteMessageType(item.id); load() }}>Delete</button></>}</td></tr>)}</tbody></table></div></section>
      </main>
    </AppLayout>
  )
}

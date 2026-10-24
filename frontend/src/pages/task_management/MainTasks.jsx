import { useEffect, useState } from 'react'
import AppLayout from '../../layouts/app_layout'
import { fetchMainTasks, saveMainTask } from '../../services/taskManagementApi'
import { fetchMessageTypeTree } from '../../services/messageTypeApi'
import './task_management.css'

const EMPTY = { name: '', source_type: 'MANUAL', message_type_id: '', weight: 10, is_active: true }
const SOURCES = [
  ['MANUAL', 'Manual'], ['MESSAGE_TYPE', 'Message type'],
  ['SOLD_POSTING', 'Sold posting'], ['OFFER_MANAGEMENT', 'Offer management'],
]

function messageOptions(nodes, prefix = '') {
  return nodes.flatMap((node) => [
    <option value={node.id} key={node.id}>{prefix}{node.name}</option>,
    ...messageOptions(node.children || [], `${prefix}${node.name} / `),
  ])
}

function findMessageType(nodes, id) {
  for (const node of nodes) {
    if (node.id === id) return node
    const child = findMessageType(node.children || [], id)
    if (child) return child
  }
  return null
}

function descendantNames(node) {
  return (node?.children || []).flatMap((child) => [child.name, ...descendantNames(child)])
}

export default function MainTasks({ currentUser, onLogout }) {
  const [tasks, setTasks] = useState([])
  const [messageTypes, setMessageTypes] = useState([])
  const [form, setForm] = useState(null)
  const [editingId, setEditingId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const selectedMessageType = form?.source_type === 'MESSAGE_TYPE' ? findMessageType(messageTypes, form.message_type_id) : null
  const includedSubtypes = descendantNames(selectedMessageType)

  async function reload() { setTasks(await fetchMainTasks()) }
  useEffect(() => {
    let active = true
    Promise.all([fetchMainTasks(), fetchMessageTypeTree()])
      .then(([items, types]) => { if (active) { setTasks(items); setMessageTypes(types) } })
      .catch((caught) => { if (active) setError(caught.message) })
    return () => { active = false }
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await saveMainTask({ ...form, name: form.name.trim(), message_type_id: form.source_type === 'MESSAGE_TYPE' ? form.message_type_id : null, weight: Number(form.weight) }, editingId)
      await reload()
      setForm(null); setEditingId(''); setNotice('Task saved for everyone.')
    } catch (caught) { setError(caught.message) }
    finally { setBusy(false) }
  }

  return <AppLayout activePage="Task Management" currentUser={currentUser} onLogout={onLogout}>
    <main className="management-page task-management-page main-tasks-page">
      <div className="page-header main-tasks-header">
        <div><h1>Task Management</h1><p>Manage the tasks and scores shared by every agent.</p></div>
        <button className="primary-button compact" type="button" onClick={() => { setEditingId(''); setForm({ ...EMPTY }) }}>+ Add Main Task</button>
      </div>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {notice ? <p className="form-message success" role="status">{notice}</p> : null}
      {form ? <form className="table-card main-task-editor" onSubmit={submit}>
        <div className="main-task-editor-heading">
          <div><h2>{editingId ? 'Edit main task' : 'Add main task'}</h2><p>Set the source and score once for the whole team.</p></div>
        </div>
        <div className="main-task-fields">
          <label className="field main-task-name"><span>Task name</span><input required maxLength="160" disabled={form.source_type === 'OTHER'} placeholder="e.g. Booking follow-up" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          <label className="field"><span>Task type</span><select value={form.source_type} disabled={form.source_type === 'OTHER'} onChange={(event) => setForm({ ...form, source_type: event.target.value, message_type_id: '' })}>
            {form.source_type === 'OTHER' ? <option value="OTHER">Other</option> : SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          {form.source_type === 'MESSAGE_TYPE' ? <label className="field main-task-message-type"><span>Message type</span><select required value={form.message_type_id || ''} onChange={(event) => setForm({ ...form, message_type_id: event.target.value })}>
            <option value="">Select message type</option>{messageOptions(messageTypes)}</select>
            <small>Select a parent type to include every message in its subtypes.</small></label> : null}
          <label className="field main-task-weight"><span>Task weight</span><input type="number" min="0.01" max="100" step="0.01" required value={form.weight} onChange={(event) => setForm({ ...form, weight: event.target.value })} />
            <small>Used when calculating the daily task score.</small></label>
          {selectedMessageType ? <div className="main-task-type-preview" role="status">
            <strong>{selectedMessageType.name} includes {includedSubtypes.length} {includedSubtypes.length === 1 ? 'subtype' : 'subtypes'}</strong>
            <p>Messages classified as {selectedMessageType.name}{includedSubtypes.length ? ' or any subtype below it' : ''} will count toward this task.</p>
            {includedSubtypes.length ? <div className="main-task-type-chips">{includedSubtypes.map((name, index) => <span key={`${name}-${index}`}>{name}</span>)}</div> : null}
          </div> : null}
          {form.source_type !== 'OTHER' ? <label className="main-task-availability"><span><strong>Available to agents</strong><small>Include this task in daily reports and scoring.</small></span>
            <input type="checkbox" role="switch" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /></label> : null}
        </div>
        <div className="main-task-editor-actions"><button className="secondary-button" type="button" onClick={() => setForm(null)}>Cancel</button>
          <button className="primary-button compact" disabled={busy}>{busy ? 'Saving…' : editingId ? 'Save Changes' : 'Create Task'}</button></div>
      </form> : null}
      <section className="table-card main-task-list" aria-label="Main tasks">
        <div className="main-task-list-heading"><div><h2>Main tasks</h2><p>These tasks are shared across all agents.</p></div><span>{tasks.length} tasks</span></div>
        <div className="table-scroll"><table className="users-table"><thead><tr><th>Task</th><th>Source</th><th>Weight</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>{tasks.map((task) => <tr key={task.id}><td><strong>{task.name}</strong></td><td>{SOURCES.find(([source]) => source === task.source_type)?.[1] || 'Other'}</td><td>{Number(task.weight).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td><td><span className={`main-task-status ${task.is_active ? 'is-active' : 'is-inactive'}`}>{task.is_active ? 'Active' : 'Inactive'}</span></td>
            <td><button className="secondary-button compact-action" type="button" onClick={() => { setEditingId(task.id); setForm({ ...task, message_type_id: task.message_type_id || '' }) }}>Edit</button></td></tr>)}</tbody></table></div>
        {!tasks.length ? <p className="main-task-empty">No main tasks yet. Add one to get started.</p> : null}
      </section>
    </main>
  </AppLayout>
}

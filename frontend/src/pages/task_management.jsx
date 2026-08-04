import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import { fetchTaskCategories, fetchUserTaskAssignments, saveSubtask, saveTaskCategory, saveUserTaskAssignment } from '../services/taskManagementApi'
import { fetchMessageTypes } from '../services/messageTypeApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

const STATUSES = ['ACTIVE', 'INACTIVE', 'ARCHIVED']
const SOURCE_TYPES = [
  ['MESSAGE_TYPE', 'Message Type'],
  ['SOLD_POSTING', 'Sold Posting'],
  ['OFFER_MANAGEMENT', 'Offer Management'],
  ['OTHER_GENERAL_WORK', 'Other General Work'],
  ['MANUAL', 'Manual / Custom'],
]
const AUTO_SOURCE_TYPES = new Set(['MESSAGE_TYPE', 'SOLD_POSTING', 'OFFER_MANAGEMENT'])
const TARGET_TYPES = ['ANY_ACTIVITY', 'FIXED_COUNT', 'COMPLETION_PERCENTAGE', 'MANUAL']
const today = () => new Date().toISOString().slice(0, 10)

function emptyCategory(order = 0) {
  return { name: '', description: '', status: 'ACTIVE', quality_weight: 0, display_order: order }
}

function emptySubtask(categoryId = '', order = 0) {
  return { task_category_id: categoryId, name: '', description: '', status: 'ACTIVE', display_order: order, source_type: 'MANUAL', source_reference_id: '', source_configuration: null, count_method: '', completion_rule: '' }
}

function emptyAssignment(userId = '') {
  return { user_id: userId, subtask_id: '', quality_weight: 0, effective_from: today(), effective_to: '', auto_fetch_enabled: true, target_type: 'ANY_ACTIVITY', target_value: '', display_order: 0, status: 'ACTIVE' }
}

function labelize(value) {
  return String(value || '').replaceAll('_', ' ')
}

function sourceLabel(value) {
  return SOURCE_TYPES.find(([key]) => key === value)?.[1] || labelize(value)
}

function flattenMessageTypes(nodes, depth = 0) {
  return (nodes || []).flatMap((node) => [{ ...node, depth }, ...flattenMessageTypes(node.children || [], depth + 1)])
}

export default function TaskManagement({ currentUser, onLogout }) {
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [messageTypes, setMessageTypes] = useState([])
  const [selectedCategoryId, setSelectedCategoryId] = useState('')
  const [categoryForm, setCategoryForm] = useState(emptyCategory())
  const [subtaskForm, setSubtaskForm] = useState(emptySubtask())
  const [selectedUserId, setSelectedUserId] = useState('')
  const [assignmentData, setAssignmentData] = useState({ total_active_weight: 0, assignments: [] })
  const [assignmentForm, setAssignmentForm] = useState(emptyAssignment())
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [editingSubtaskId, setEditingSubtaskId] = useState('')
  const [editingAssignmentId, setEditingAssignmentId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const selectedCategory = categories.find((item) => item.id === selectedCategoryId)
  const activeMessageTypes = useMemo(() => flattenMessageTypes(messageTypes).filter((item) => item.is_active && !item.is_deleted), [messageTypes])
  const agentUsers = users.filter((user) => normalizeRole(user.role) === 'AGENT' && user.is_active !== false)
  const displayWeight = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })

  const allSubtasks = useMemo(() => categories.flatMap((category) => (category.subtasks || []).map((subtask) => ({ ...subtask, category_name: category.name }))), [categories])
  const assignableSubtasks = useMemo(() => allSubtasks.filter((subtask) => subtask.status === 'ACTIVE'), [allSubtasks])

  async function load() {
    try {
      const [categoryData, userData, messageTypeData] = await Promise.all([fetchTaskCategories(), fetchUsers(), fetchMessageTypes(false)])
      setCategories(categoryData || [])
      setUsers(userData.items || userData || [])
      setMessageTypes(messageTypeData || [])
      setError('')
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function loadAssignments(userId = selectedUserId) {
    if (!userId) return
    try {
      setAssignmentData(await fetchUserTaskAssignments(userId))
      setError('')
    } catch (caught) {
      setError(caught.message)
    }
  }

  useEffect(() => { load() }, [])

  async function submitCategory(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      await saveTaskCategory({ ...categoryForm, quality_weight: Number(categoryForm.quality_weight) || 0, display_order: Number(categoryForm.display_order) || 0 }, editingCategoryId)
      setCategoryForm(emptyCategory(categories.length + 1))
      setEditingCategoryId('')
      setMessage('Task category saved.')
      await load()
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function submitSubtask(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      if (subtaskForm.source_type === 'MESSAGE_TYPE' && !subtaskForm.source_reference_id) {
        setError('Select a Message Type for this subtask.')
        return
      }
      const payload = {
        ...subtaskForm,
        task_category_id: subtaskForm.task_category_id || selectedCategoryId,
        display_order: Number(subtaskForm.display_order) || 0,
        source_reference_id: subtaskForm.source_type === 'MESSAGE_TYPE' ? (subtaskForm.source_reference_id || null) : null,
        source_configuration: subtaskForm.source_configuration || null,
      }
      await saveSubtask(payload, editingSubtaskId)
      setSubtaskForm(emptySubtask(selectedCategoryId, (selectedCategory?.subtasks || []).length + 1))
      setEditingSubtaskId('')
      setMessage('Subtask saved.')
      await load()
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function submitAssignment(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      const payload = {
        ...assignmentForm,
        user_id: assignmentForm.user_id || selectedUserId,
        quality_weight: Number(assignmentForm.quality_weight) || 0,
        target_value: assignmentForm.target_value === '' ? null : Number(assignmentForm.target_value),
        display_order: Number(assignmentForm.display_order) || 0,
        effective_to: assignmentForm.effective_to || null,
      }
      await saveUserTaskAssignment(payload, editingAssignmentId)
      setAssignmentForm(emptyAssignment(selectedUserId))
      setEditingAssignmentId('')
      setMessage('Task assignment saved.')
      await loadAssignments(selectedUserId)
    } catch (caught) {
      setError(caught.message)
    }
  }

  function editCategory(category) {
    setSelectedCategoryId(category.id)
    setEditingCategoryId(category.id)
    setCategoryForm({ name: category.name, description: category.description || '', status: category.status, quality_weight: category.quality_weight || 0, display_order: category.display_order || 0 })
    setSubtaskForm(emptySubtask(category.id, (category.subtasks || []).length + 1))
  }

  function editSubtask(subtask) {
    setEditingSubtaskId(subtask.id)
    setSubtaskForm({ ...subtask, source_reference_id: subtask.source_reference_id || '', source_configuration: subtask.source_configuration || null, count_method: subtask.count_method || '', completion_rule: subtask.completion_rule || '' })
  }

  function editAssignment(assignment) {
    setEditingAssignmentId(assignment.id)
    setAssignmentForm({
      user_id: selectedUserId,
      subtask_id: assignment.subtask_id,
      quality_weight: assignment.quality_weight || 0,
      effective_from: assignment.effective_from,
      effective_to: assignment.effective_to || '',
      auto_fetch_enabled: assignment.auto_fetch_enabled,
      target_type: assignment.target_type,
      target_value: assignment.target_value ?? '',
      display_order: assignment.display_order || 0,
      status: assignment.status,
    })
  }

  function cancelAssignmentEdit() {
    setEditingAssignmentId('')
    setAssignmentForm(emptyAssignment(selectedUserId))
  }

  return (
    <AppLayout activePage="Task Management" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page task-management-page">
        <div className="page-header"><div><h1>Task Management</h1><p>Configure scoring tasks, subtasks and agent weights</p></div><button className="secondary-button compact-action" type="button" onClick={load}>Refresh</button></div>
        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}
        <section className="task-management-grid">
          <section className="table-card task-list-panel">
            <div className="pms-card-header"><h2>Task Categories</h2></div>
            <div className="task-category-list">
              {categories.map((category) => <button className={category.id === selectedCategoryId ? 'selected' : ''} type="button" key={category.id} onClick={() => editCategory(category)}><span><strong>{category.name}</strong><small>{labelize(category.status)} - {(category.subtasks || []).length} subtasks</small></span><Icon name="chevron" /></button>)}
            </div>
            <form className="management-form" onSubmit={submitCategory}>
              <h3>{editingCategoryId ? 'Edit Category' : 'Add Category'}</h3>
              <label className="field"><span>Name</span><input value={categoryForm.name} onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))} required /></label>
              <label className="field"><span>Description</span><textarea value={categoryForm.description} onChange={(event) => setCategoryForm((current) => ({ ...current, description: event.target.value }))} /></label>
              <div className="pms-form-row"><label className="field"><span>Status</span><select value={categoryForm.status} onChange={(event) => setCategoryForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Display Order</span><input type="number" value={categoryForm.display_order} onChange={(event) => setCategoryForm((current) => ({ ...current, display_order: event.target.value }))} /></label></div>
              <button className="primary-button compact-action" type="submit">Save Category</button>
            </form>
          </section>

          <section className="table-card">
            <div className="pms-card-header"><h2>{selectedCategory ? `${selectedCategory.name} Subtasks` : 'Subtasks'}</h2></div>
            <div className="table-scroll"><table className="users-table"><thead><tr><th>Name</th><th>Source</th><th>Status</th><th>Assignments</th><th></th></tr></thead><tbody>{(selectedCategory?.subtasks || []).map((subtask) => <tr key={subtask.id}><td>{subtask.name}</td><td>{sourceLabel(subtask.source_type)}{subtask.source_type === 'MESSAGE_TYPE' ? ` \u2192 ${activeMessageTypes.find((item) => item.id === subtask.source_reference_id)?.name || 'Unknown'}` : ''}</td><td>{labelize(subtask.status)}</td><td>{subtask.assignment_count}</td><td><button className="icon-button" type="button" onClick={() => editSubtask(subtask)}><Icon name="edit" /></button></td></tr>)}</tbody></table></div>
            <form className="management-form task-subtask-form" onSubmit={submitSubtask}>
              <h3>{editingSubtaskId ? 'Edit Subtask' : 'Add Subtask'}</h3>
              <label className="field"><span>Category</span><select value={subtaskForm.task_category_id || selectedCategoryId} onChange={(event) => setSubtaskForm((current) => ({ ...current, task_category_id: event.target.value }))} required><option value="">Select category</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
              <label className="field"><span>Name</span><input value={subtaskForm.name} onChange={(event) => setSubtaskForm((current) => ({ ...current, name: event.target.value }))} required /></label>
              <div className="pms-form-row">
                <label className="field">
                  <span>Source</span>
                  <select value={subtaskForm.source_type} onChange={(event) => setSubtaskForm((current) => ({ ...current, source_type: event.target.value, source_reference_id: event.target.value === 'MESSAGE_TYPE' ? current.source_reference_id : '' }))}>
                    {SOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="field"><span>Status</span><select value={subtaskForm.status} onChange={(event) => setSubtaskForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label>
              </div>
              {subtaskForm.source_type === 'MESSAGE_TYPE' ? (
                <label className="field">
                  <span>Message Type</span>
                  <select value={subtaskForm.source_reference_id} onChange={(event) => setSubtaskForm((current) => ({ ...current, source_reference_id: event.target.value }))} required>
                    <option value="">Select message type</option>
                    {activeMessageTypes.map((item) => <option key={item.id} value={item.id}>{'\u2014 '.repeat(item.depth)}{item.name}</option>)}
                  </select>
                </label>
              ) : null}
              <p className="field-help">{AUTO_SOURCE_TYPES.has(subtaskForm.source_type) ? 'This subtask will be automatically fetched on Daily Task Entry.' : 'This subtask requires manual score entry on Daily Task Entry.'}</p>
              <label className="field"><span>Display Order</span><input type="number" value={subtaskForm.display_order} onChange={(event) => setSubtaskForm((current) => ({ ...current, display_order: event.target.value }))} /></label>
              <label className="field"><span>Description</span><textarea value={subtaskForm.description || ''} onChange={(event) => setSubtaskForm((current) => ({ ...current, description: event.target.value }))} /></label>
              <button className="primary-button compact-action" type="submit">Save Subtask</button>
            </form>
          </section>

          <section className="table-card task-assignment-panel">
            <div className="pms-card-header"><h2>Agent Task Assignments</h2><span className={assignmentData.total_active_weight === 100 ? 'weight-ok' : assignmentData.total_active_weight > 100 ? 'weight-error' : 'weight-warning'}>Quality Weight Total: {displayWeight(assignmentData.total_active_weight)}/100</span></div>
            <label className="field"><span>Agent</span><select value={selectedUserId} onChange={(event) => { setSelectedUserId(event.target.value); cancelAssignmentEdit(); setAssignmentForm(emptyAssignment(event.target.value)); loadAssignments(event.target.value) }}><option value="">Select agent</option>{agentUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name} - {user.email}</option>)}</select></label>
            <div className="table-scroll"><table className="users-table task-assignment-table"><thead><tr><th>Task</th><th>Subtask</th><th>Source</th><th>Weight</th><th>Dates</th><th>Status</th><th></th></tr></thead><tbody>{(assignmentData.assignments || []).map((assignment) => <tr key={assignment.id}><td>{assignment.category_name}</td><td>{assignment.subtask_name}</td><td>{sourceLabel(assignment.source_type)}</td><td>{displayWeight(assignment.quality_weight)}</td><td>{assignment.effective_from}{assignment.effective_to ? ` to ${assignment.effective_to}` : ''}</td><td>{labelize(assignment.status)}</td><td><button className="icon-button" type="button" onClick={() => editAssignment(assignment)}><Icon name="edit" /></button></td></tr>)}</tbody></table></div>
            <form className="management-form" onSubmit={submitAssignment}>
              <h3>{editingAssignmentId ? 'Edit Assignment' : 'Assign Subtask'}</h3>
              <label className="field"><span>Subtask</span><select value={assignmentForm.subtask_id} onChange={(event) => setAssignmentForm((current) => ({ ...current, subtask_id: event.target.value }))} required><option value="">Select subtask</option>{assignableSubtasks.map((subtask) => <option key={subtask.id} value={subtask.id}>{subtask.category_name} - {subtask.name} ({sourceLabel(subtask.source_type)})</option>)}</select></label>
              <div className="pms-form-row"><label className="field"><span>Weight / Max Score</span><input type="number" min="0" max="100" step="0.01" value={assignmentForm.quality_weight} onChange={(event) => setAssignmentForm((current) => ({ ...current, quality_weight: event.target.value }))} required /></label><label className="field"><span>Status</span><select value={assignmentForm.status} onChange={(event) => setAssignmentForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label></div>
              <div className="pms-form-row"><label className="field"><span>Effective From</span><input type="date" value={assignmentForm.effective_from} onChange={(event) => setAssignmentForm((current) => ({ ...current, effective_from: event.target.value }))} required /></label><label className="field"><span>Effective To</span><input type="date" value={assignmentForm.effective_to || ''} onChange={(event) => setAssignmentForm((current) => ({ ...current, effective_to: event.target.value }))} /></label></div>
              <div className="pms-form-row"><label className="field"><span>Target Rule</span><select value={assignmentForm.target_type} onChange={(event) => setAssignmentForm((current) => ({ ...current, target_type: event.target.value }))}>{TARGET_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Target Value</span><input type="number" min="0" value={assignmentForm.target_value ?? ''} onChange={(event) => setAssignmentForm((current) => ({ ...current, target_value: event.target.value }))} /></label></div>
              <label className="checkbox-field"><input type="checkbox" checked={assignmentForm.auto_fetch_enabled} onChange={(event) => setAssignmentForm((current) => ({ ...current, auto_fetch_enabled: event.target.checked }))} /> Auto fetch enabled</label>
              <div className="pms-form-row">
                <button className="primary-button compact-action" type="submit" disabled={!selectedUserId}>{editingAssignmentId ? 'Save Assignment' : 'Add Assignment'}</button>
                {editingAssignmentId ? <button className="secondary-button compact-action" type="button" onClick={cancelAssignmentEdit}>Cancel</button> : null}
              </div>
            </form>
          </section>
        </section>
      </main>
    </AppLayout>
  )
}
import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import { fetchTaskCategories, fetchUserTaskAssignments, saveSubtask, saveTaskCategory, saveTaskCategoryAssignment } from '../services/taskManagementApi'
import { fetchUsers } from '../services/userApi'
import { normalizeRole } from '../utils/roles'

const STATUSES = ['ACTIVE', 'INACTIVE', 'ARCHIVED']
const SOURCE_TYPES = ['MESSAGE_CATEGORY', 'CONVERSATION_CATEGORY', 'SOLD_POSTING', 'PRICING_UPDATE', 'QUANTITY_SYNC', 'BOOKING', 'INVOICE', 'TRACKING', 'PURCHASE', 'MANUAL', 'CUSTOM']
const TARGET_TYPES = ['ANY_ACTIVITY', 'FIXED_COUNT', 'COMPLETION_PERCENTAGE', 'MANUAL']
const today = () => new Date().toISOString().slice(0, 10)

function emptyCategory(order = 0) {
  return { name: '', description: '', status: 'ACTIVE', quality_weight: 0, display_order: order }
}

function emptySubtask(categoryId = '', order = 0) {
  return { task_category_id: categoryId, name: '', description: '', status: 'ACTIVE', display_order: order, source_type: 'MANUAL', source_reference_id: '', source_configuration: null, count_method: '', completion_rule: '', supports_automatic_fetch: false }
}

function emptyAssignment(userId = '', categoryId = '') {
  return { user_id: userId, task_category_id: categoryId, effective_from: today(), effective_to: '', auto_fetch_enabled: true, target_type: 'ANY_ACTIVITY', target_value: '', display_order: 0, status: 'ACTIVE' }
}

function labelize(value) {
  return String(value || '').replaceAll('_', ' ')
}

export default function TaskManagement({ currentUser, onLogout }) {
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [selectedCategoryId, setSelectedCategoryId] = useState('')
  const [categoryForm, setCategoryForm] = useState(emptyCategory())
  const [subtaskForm, setSubtaskForm] = useState(emptySubtask())
  const [selectedUserId, setSelectedUserId] = useState('')
  const [assignmentData, setAssignmentData] = useState({ total_active_weight: 0, assignments: [] })
  const [assignmentForm, setAssignmentForm] = useState(emptyAssignment())
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [editingSubtaskId, setEditingSubtaskId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const selectedCategory = categories.find((item) => item.id === selectedCategoryId)
  const assignableCategories = useMemo(() => categories.filter((category) => category.status === 'ACTIVE' && (category.subtasks || []).some((subtask) => subtask.status === 'ACTIVE')), [categories])
  const agentUsers = users.filter((user) => normalizeRole(user.role) === 'AGENT' && user.is_active !== false)
  const displayWeight = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })

  async function load() {
    try {
      const [categoryData, userData] = await Promise.all([fetchTaskCategories(), fetchUsers()])
      setCategories(categoryData || [])
      setUsers(userData.items || userData || [])
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
      const payload = {
        ...subtaskForm,
        task_category_id: subtaskForm.task_category_id || selectedCategoryId,
        display_order: Number(subtaskForm.display_order) || 0,
        source_reference_id: subtaskForm.source_reference_id || null,
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
        target_value: assignmentForm.target_value === '' ? null : Number(assignmentForm.target_value),
        display_order: Number(assignmentForm.display_order) || 0,
        effective_to: assignmentForm.effective_to || null,
      }
      const savedSummary = await saveTaskCategoryAssignment(payload)
      setAssignmentForm(emptyAssignment(selectedUserId))
      setAssignmentData(savedSummary)
      setMessage('Task assignment saved.')
      await load()
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
              {categories.map((category) => <button className={category.id === selectedCategoryId ? 'selected' : ''} type="button" key={category.id} onClick={() => editCategory(category)}><span><strong>{category.name}</strong><small>{labelize(category.status)} - {displayWeight(category.quality_weight)} weight - {(category.subtasks || []).length} subtasks</small></span><Icon name="chevron" /></button>)}
            </div>
            <form className="management-form" onSubmit={submitCategory}>
              <h3>{editingCategoryId ? 'Edit Category' : 'Add Category'}</h3>
              <label className="field"><span>Name</span><input value={categoryForm.name} onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))} required /></label>
              <label className="field"><span>Description</span><textarea value={categoryForm.description} onChange={(event) => setCategoryForm((current) => ({ ...current, description: event.target.value }))} /></label>
              <div className="pms-form-row"><label className="field"><span>Weight</span><input type="number" min="0" max="100" step="0.01" value={categoryForm.quality_weight} onChange={(event) => setCategoryForm((current) => ({ ...current, quality_weight: event.target.value }))} /></label><label className="field"><span>Status</span><select value={categoryForm.status} onChange={(event) => setCategoryForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Display Order</span><input type="number" value={categoryForm.display_order} onChange={(event) => setCategoryForm((current) => ({ ...current, display_order: event.target.value }))} /></label></div>
              <button className="primary-button compact-action" type="submit">Save Category</button>
            </form>
          </section>

          <section className="table-card">
            <div className="pms-card-header"><h2>{selectedCategory ? `${selectedCategory.name} Subtasks` : 'Subtasks'}</h2></div>
            <div className="table-scroll"><table className="users-table"><thead><tr><th>Name</th><th>Source</th><th>Status</th><th>Weight Uses</th><th></th></tr></thead><tbody>{(selectedCategory?.subtasks || []).map((subtask) => <tr key={subtask.id}><td>{subtask.name}</td><td>{labelize(subtask.source_type)}</td><td>{labelize(subtask.status)}</td><td>{subtask.assignment_count}</td><td><button className="icon-button" type="button" onClick={() => editSubtask(subtask)}><Icon name="edit" /></button></td></tr>)}</tbody></table></div>
            <form className="management-form task-subtask-form" onSubmit={submitSubtask}>
              <h3>{editingSubtaskId ? 'Edit Subtask' : 'Add Subtask'}</h3>
              <label className="field"><span>Category</span><select value={subtaskForm.task_category_id || selectedCategoryId} onChange={(event) => setSubtaskForm((current) => ({ ...current, task_category_id: event.target.value }))} required><option value="">Select category</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
              <label className="field"><span>Name</span><input value={subtaskForm.name} onChange={(event) => setSubtaskForm((current) => ({ ...current, name: event.target.value }))} required /></label>
              <div className="pms-form-row"><label className="field"><span>Source Type</span><select value={subtaskForm.source_type} onChange={(event) => setSubtaskForm((current) => ({ ...current, source_type: event.target.value }))}>{SOURCE_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Status</span><select value={subtaskForm.status} onChange={(event) => setSubtaskForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label></div>
              <div className="pms-form-row"><label className="field"><span>Display Order</span><input type="number" value={subtaskForm.display_order} onChange={(event) => setSubtaskForm((current) => ({ ...current, display_order: event.target.value }))} /></label><label className="checkbox-field"><input type="checkbox" checked={subtaskForm.supports_automatic_fetch} onChange={(event) => setSubtaskForm((current) => ({ ...current, supports_automatic_fetch: event.target.checked }))} /> Supports automatic fetch</label></div>
              <label className="field"><span>Description</span><textarea value={subtaskForm.description || ''} onChange={(event) => setSubtaskForm((current) => ({ ...current, description: event.target.value }))} /></label>
              <button className="primary-button compact-action" type="submit">Save Subtask</button>
            </form>
          </section>

          <section className="table-card task-assignment-panel">
            <div className="pms-card-header"><h2>Agent Task Assignments</h2><span className={assignmentData.total_active_weight === 100 ? 'weight-ok' : assignmentData.total_active_weight > 100 ? 'weight-error' : 'weight-warning'}>Quality Weight Total: {displayWeight(assignmentData.total_active_weight)}/100</span></div>
            <label className="field"><span>Agent</span><select value={selectedUserId} onChange={(event) => { setSelectedUserId(event.target.value); setAssignmentForm(emptyAssignment(event.target.value)); loadAssignments(event.target.value) }}><option value="">Select agent</option>{agentUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name} - {user.email}</option>)}</select></label>
            <div className="table-scroll"><table className="users-table task-assignment-table"><thead><tr><th>Task</th><th>Managed Subtask</th><th>Assigned Weight</th><th>Dates</th><th>Status</th></tr></thead><tbody>{(assignmentData.assignments || []).map((assignment) => <tr key={assignment.id}><td>{assignment.category_name}</td><td>{assignment.subtask_name}</td><td>{displayWeight(assignment.quality_weight)}</td><td>{assignment.effective_from}{assignment.effective_to ? ` to ${assignment.effective_to}` : ''}</td><td>{labelize(assignment.status)}</td></tr>)}</tbody></table></div>
            <form className="management-form" onSubmit={submitAssignment}>
              <h3>Assign Task</h3>
              <label className="field"><span>Task Category</span><select value={assignmentForm.task_category_id} onChange={(event) => setAssignmentForm((current) => ({ ...current, task_category_id: event.target.value }))} required><option value="">Select task</option>{assignableCategories.map((category) => <option key={category.id} value={category.id}>{category.name} - {(category.subtasks || []).filter((subtask) => subtask.status === 'ACTIVE').length} subtasks</option>)}</select></label>
              <p className="field-help">The saved task weight is split across all active subtasks in this category.</p>
              <div className="pms-form-row"><label className="field"><span>Status</span><select value={assignmentForm.status} onChange={(event) => setAssignmentForm((current) => ({ ...current, status: event.target.value }))}>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label></div>
              <div className="pms-form-row"><label className="field"><span>Effective From</span><input type="date" value={assignmentForm.effective_from} onChange={(event) => setAssignmentForm((current) => ({ ...current, effective_from: event.target.value }))} required /></label><label className="field"><span>Effective To</span><input type="date" value={assignmentForm.effective_to || ''} onChange={(event) => setAssignmentForm((current) => ({ ...current, effective_to: event.target.value }))} /></label></div>
              <div className="pms-form-row"><label className="field"><span>Target Rule</span><select value={assignmentForm.target_type} onChange={(event) => setAssignmentForm((current) => ({ ...current, target_type: event.target.value }))}>{TARGET_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Target Value</span><input type="number" min="0" value={assignmentForm.target_value ?? ''} onChange={(event) => setAssignmentForm((current) => ({ ...current, target_value: event.target.value }))} /></label></div>
              <label className="checkbox-field"><input type="checkbox" checked={assignmentForm.auto_fetch_enabled} onChange={(event) => setAssignmentForm((current) => ({ ...current, auto_fetch_enabled: event.target.checked }))} /> Auto fetch enabled</label>
              <button className="primary-button compact-action" type="submit" disabled={!selectedUserId}>Save Assignment</button>
            </form>
          </section>
        </section>
      </main>
    </AppLayout>
  )
}

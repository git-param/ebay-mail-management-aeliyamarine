import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { deleteSubtask, deleteTaskCategory, fetchTaskCategories, fetchUserTaskAssignments, saveSubtask, saveTaskAssignment, saveTaskCategory } from '../../services/taskManagementApi'
import { fetchMessageTypes } from '../../services/messageTypeApi'
import { fetchUsers } from '../../services/userApi'
import { normalizeRole } from '../../utils/roles'

import './task_management.css'

const STATUSES = ['ACTIVE', 'INACTIVE', 'ARCHIVED']
const SOURCE_TYPES = [
  ['MESSAGE_TYPE', 'Message Type'],
  ['SOLD_POSTING', 'Sold Posting'],
  ['OFFER_MANAGEMENT', 'Offer Management'],
  ['OTHER_GENERAL_WORK', 'Other General Work'],
  ['MANUAL', 'Manual / Custom'],
]
const AUTO_SOURCE_TYPES = new Set(['MESSAGE_TYPE', 'SOLD_POSTING', 'OFFER_MANAGEMENT'])
const today = () => new Date().toISOString().slice(0, 10)

function emptyCategory() {
  return { name: '', description: '', status: 'ACTIVE', quality_weight: 0 }
}

function emptySubtask(categoryId = '') {
  return {
    task_category_id: categoryId,
    name: '',
    description: '',
    status: 'ACTIVE',
    source_type: 'MANUAL',
    source_reference_id: '',
    source_configuration: null,
    count_method: '',
    completion_rule: '',
  }
}

function emptyTaskAssignment(userId = '') {
  return {
    user_id: userId,
    task_category_id: '',
    effective_from: today(),
    effective_to: '',
    auto_fetch_enabled: true,
    status: 'ACTIVE',
  }
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

function taskSummaryForm(category) {
  return {
    name: category.name,
    description: category.description || '',
    status: category.status,
    quality_weight: Number(category.quality_weight || 0),
  }
}

function subtaskSummaryForm(subtask) {
  return {
    task_category_id: subtask.task_category_id,
    name: subtask.name,
    description: subtask.description || '',
    status: subtask.status,
    source_type: subtask.source_type,
    source_reference_id: subtask.source_reference_id || '',
    source_configuration: subtask.source_configuration || null,
    count_method: subtask.count_method || '',
    completion_rule: subtask.completion_rule || '',
  }
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
  const [taskAssignmentForm, setTaskAssignmentForm] = useState(emptyTaskAssignment())
  const [subtaskWeights, setSubtaskWeights] = useState({})
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [editingSubtaskId, setEditingSubtaskId] = useState('')
  const [assigningTaskId, setAssigningTaskId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const selectedCategory = useMemo(() => categories.find((item) => item.id === selectedCategoryId) || null, [categories, selectedCategoryId])
  const activeMessageTypes = useMemo(() => flattenMessageTypes(messageTypes).filter((item) => item.is_active && !item.is_deleted), [messageTypes])
  const agentUsers = users.filter((user) => normalizeRole(user.role) === 'AGENT' && user.is_active !== false)
  const displayWeight = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })

  const currentAssignments = assignmentData.assignments || []
  const assignmentGroupsByCategory = useMemo(() => {
    const groups = new Map()
    for (const assignment of currentAssignments) {
      const key = assignment.category_name || 'Unassigned'
      if (!groups.has(key)) {
        groups.set(key, { categoryName: key, assignments: [], taskCategoryId: assignment.task_category_id })
      }
      groups.get(key).assignments.push(assignment)
    }
    return Array.from(groups.values())
  }, [currentAssignments])
  const currentAssignmentGroup = assignmentGroupsByCategory[0] || null
  const assignmentCategory = categories.find((item) => item.id === taskAssignmentForm.task_category_id)
  const assignableSubtasksForForm = useMemo(() => (assignmentCategory?.subtasks || []).filter((subtask) => subtask.status === 'ACTIVE'), [assignmentCategory])
  const assignedSubtaskIdsForUser = useMemo(() => new Set(currentAssignments.map((item) => item.subtask_id)), [currentAssignments])

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

  function createNewTask() {
    setSelectedCategoryId('')
    setEditingCategoryId('')
    setCategoryForm(emptyCategory())
    setEditingSubtaskId('')
    setSubtaskForm(emptySubtask())
  }

  function openTask(category) {
    if (!category) {
      createNewTask()
      return
    }
    setSelectedCategoryId(category.id)
    setEditingCategoryId(category.id)
    setCategoryForm(taskSummaryForm(category))
    setEditingSubtaskId('')
    setSubtaskForm(emptySubtask(category.id))
  }

  async function submitCategory(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      const payload = {
        ...categoryForm,
        quality_weight: Number(categoryForm.quality_weight) || 0,
      }
      const saved = await saveTaskCategory(payload, editingCategoryId)
      await load()
      setSelectedCategoryId(saved.id)
      setEditingCategoryId(saved.id)
      setCategoryForm(taskSummaryForm(saved))
      setSubtaskForm(emptySubtask(saved.id))
      setMessage(editingCategoryId ? 'Task updated.' : 'Task created with a default Other subtask.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function deleteCategory(category) {
    if (!category) return
    if (!window.confirm(`Delete task "${category.name}"? This also removes its subtasks and assignments.`)) return
    try {
      setError('')
      setMessage('')
      await deleteTaskCategory(category.id)
      if (selectedCategoryId === category.id) {
        createNewTask()
      }
      await load()
      setMessage('Task deleted.')
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
      const categoryId = subtaskForm.task_category_id || selectedCategoryId
      if (!categoryId) {
        setError('Select a task before adding a subtask.')
        return
      }
      const payload = {
        ...subtaskForm,
        task_category_id: categoryId,
        source_reference_id: subtaskForm.source_type === 'MESSAGE_TYPE' ? (subtaskForm.source_reference_id || null) : null,
        source_configuration: subtaskForm.source_configuration || null,
      }
      await saveSubtask(payload, editingSubtaskId)
      await load()
      setSelectedCategoryId(categoryId)
      setEditingSubtaskId('')
      setSubtaskForm(emptySubtask(categoryId))
      setMessage('Subtask saved.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function deleteSubtaskItem(subtask) {
    if (!subtask) return
    if (!window.confirm(`Delete subtask "${subtask.name}"?`)) return
    try {
      setError('')
      setMessage('')
      await deleteSubtask(subtask.id)
      if (editingSubtaskId === subtask.id) {
        setEditingSubtaskId('')
        setSubtaskForm(emptySubtask(subtask.task_category_id))
      }
      await load()
      setMessage('Subtask deleted.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  function editSubtask(subtask) {
    setSelectedCategoryId(subtask.task_category_id)
    setEditingSubtaskId(subtask.id)
    setSubtaskForm(subtaskSummaryForm(subtask))
  }

  function startTaskAssignment(categoryId) {
    const category = categories.find((item) => item.id === categoryId)
    const initialWeights = {}
    for (const subtask of (category?.subtasks || []).filter((item) => item.status === 'ACTIVE')) {
      const existing = currentAssignments.find((item) => item.subtask_id === subtask.id)
      initialWeights[subtask.id] = existing ? existing.quality_weight : 0
    }
    setAssigningTaskId(categoryId)
    setTaskAssignmentForm({ ...emptyTaskAssignment(selectedUserId), task_category_id: categoryId })
    setSubtaskWeights(initialWeights)
  }

  function cancelTaskAssignment() {
    setAssigningTaskId('')
    setTaskAssignmentForm(emptyTaskAssignment(selectedUserId))
    setSubtaskWeights({})
  }

  async function submitTaskAssignment(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      if (!taskAssignmentForm.task_category_id) {
        setError('Select a task to assign.')
        return
      }
      if (!assignableSubtasksForForm.length) {
        setError('This task has no active subtasks to assign.')
        return
      }
      const subtaskWeightList = assignableSubtasksForForm.map((subtask) => ({
        subtask_id: subtask.id,
        quality_weight: Number(subtaskWeights[subtask.id]) || 0,
      }))
      const payload = {
        user_id: taskAssignmentForm.user_id || selectedUserId,
        task_category_id: taskAssignmentForm.task_category_id,
        subtask_weights: subtaskWeightList,
        effective_from: taskAssignmentForm.effective_from,
        effective_to: taskAssignmentForm.effective_to || null,
        auto_fetch_enabled: taskAssignmentForm.auto_fetch_enabled,
        status: taskAssignmentForm.status,
      }
      const saved = await saveTaskAssignment(payload)
      setAssignmentData(saved)
      setTaskAssignmentForm(emptyTaskAssignment(selectedUserId))
      setSubtaskWeights({})
      setAssigningTaskId('')
      setMessage(`Task "${assignmentCategory?.name || 'selected task'}" assigned to the agent and replaced the previous task.`)
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function handleUserChange(event) {
    const userId = event.target.value
    setSelectedUserId(userId)
    cancelTaskAssignment()
    if (userId) {
      await loadAssignments(userId)
    } else {
      setAssignmentData({ total_active_weight: 0, assignments: [] })
    }
  }

  function handleTaskSelection(event) {
    const categoryId = event.target.value
    if (!categoryId) {
      createNewTask()
      return
    }
    openTask(categories.find((item) => item.id === categoryId) || null)
  }

  return (
    <AppLayout activePage="Task Management" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page task-management-page">
        <div className="page-header">
          <div>
            <h1>Task Management</h1>
            <p>Configure tasks, subtasks, and agent maximum scores.</p>
          </div>
          <button className="secondary-button compact-action" type="button" onClick={load}>Refresh</button>
        </div>

        {error ? <p className="form-message error">{error}</p> : null}
        {message ? <p className="form-message success">{message}</p> : null}

        <section className="task-management-grid">
          <section className="table-card task-editor-panel">
            <div className="pms-card-header">
              <div>
                <h2>Tasks</h2>
                <p className="task-section-note">Select a task to edit it, or create a new one and the backend will add a default Other subtask.</p>
              </div>
              <div className="task-toolbar-actions">
                <button className="danger-button compact-action" type="button" onClick={() => deleteCategory(selectedCategory)} disabled={!selectedCategory}>
                  <Icon name="trash" />
                </button>
              </div>
            </div>

            <label className="field task-selector-field">
              <span>Task</span>
              <select value={selectedCategoryId} onChange={handleTaskSelection}>
                <option value="">Create New Task</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </label>

            <form className="management-form task-management-form" onSubmit={submitCategory}>
              <h3>{editingCategoryId ? 'Edit Task' : 'Create Task'}</h3>
              <label className="field">
                <span>Name</span>
                <input value={categoryForm.name} onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))} required />
              </label>
              <label className="field">
                <span>Description</span>
                <textarea value={categoryForm.description} onChange={(event) => setCategoryForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
              <label className="field">
                <span>Status</span>
                <select value={categoryForm.status} onChange={(event) => setCategoryForm((current) => ({ ...current, status: event.target.value }))}>
                  {STATUSES.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <button className="primary-button compact-action" type="submit">{editingCategoryId ? 'Save Task' : 'Create Task'}</button>
            </form>
          </section>

          <section className="table-card task-subtask-panel">
            <div className="pms-card-header">
              <div>
                <h2>{selectedCategory ? `${selectedCategory.name} Subtasks` : 'Subtasks'}</h2>
                <p className="task-section-note">Admins can edit, activate, deactivate, or delete subtasks here.</p>
              </div>
            </div>

            <div className="task-table-scroll" role="region" aria-label="Subtasks table" tabIndex="0">
              <table className="users-table task-subtask-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Assignments</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedCategory?.subtasks || []).map((subtask) => (
                    <tr key={subtask.id}>
                      <td>
                        <strong>{subtask.name}</strong>
                        {subtask.name.toLowerCase() === 'other' ? <div className="row-meta">Default catch-all subtask</div> : null}
                      </td>
                      <td>
                        {sourceLabel(subtask.source_type)}
                        {subtask.source_type === 'MESSAGE_TYPE' ? ` · ${activeMessageTypes.find((item) => item.id === subtask.source_reference_id)?.name || 'Unknown'}` : ''}
                      </td>
                      <td>{labelize(subtask.status)}</td>
                      <td>{subtask.assignment_count}</td>
                      <td>
                        <div className="row-actions">
                          <button className="icon-button" type="button" onClick={() => editSubtask(subtask)} title="Edit subtask"><Icon name="edit" /></button>
                          <button className="icon-button danger-icon" type="button" onClick={() => deleteSubtaskItem(subtask)} title="Delete subtask"><Icon name="trash" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <form className="management-form task-subtask-form" onSubmit={submitSubtask}>
              <h3>{editingSubtaskId ? 'Edit Subtask' : 'Add Subtask'}</h3>
              <label className="field">
                <span>Category</span>
                <select value={subtaskForm.task_category_id || selectedCategoryId} onChange={(event) => setSubtaskForm((current) => ({ ...current, task_category_id: event.target.value }))} required>
                  <option value="">Select category</option>
                  {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Name</span>
                <input value={subtaskForm.name} onChange={(event) => setSubtaskForm((current) => ({ ...current, name: event.target.value }))} required />
              </label>
              <div className="pms-form-row">
                <label className="field">
                  <span>Source</span>
                  <select value={subtaskForm.source_type} onChange={(event) => setSubtaskForm((current) => ({ ...current, source_type: event.target.value, source_reference_id: event.target.value === 'MESSAGE_TYPE' ? current.source_reference_id : '' }))}>
                    {SOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select value={subtaskForm.status} onChange={(event) => setSubtaskForm((current) => ({ ...current, status: event.target.value }))}>
                    {STATUSES.map((item) => <option key={item}>{item}</option>)}
                  </select>
                </label>
              </div>
              {subtaskForm.source_type === 'MESSAGE_TYPE' ? (
                <label className="field">
                  <span>Message Type</span>
                  <select value={subtaskForm.source_reference_id} onChange={(event) => setSubtaskForm((current) => ({ ...current, source_reference_id: event.target.value }))} required>
                    <option value="">Select message type</option>
                    {activeMessageTypes.map((item) => <option key={item.id} value={item.id}>{'  '.repeat(item.depth)}{item.name}</option>)}
                  </select>
                </label>
              ) : null}
              <p className="field-help">{AUTO_SOURCE_TYPES.has(subtaskForm.source_type) ? 'This subtask will be automatically fetched on Daily Task Entry.' : 'This subtask requires manual score entry on Daily Task Entry.'}</p>
              <label className="field">
                <span>Description</span>
                <textarea value={subtaskForm.description || ''} onChange={(event) => setSubtaskForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
              <button className="primary-button compact-action" type="submit">{editingSubtaskId ? 'Save Subtask' : 'Add Subtask'}</button>
            </form>
          </section>

          <section className="table-card task-assignment-panel">
            <div className="pms-card-header">
              <div>
                <h2>Agent Task Assignments</h2>
                <p className="task-section-note">Assigning a task replaces the agent's current task and all of its active subtasks.</p>
              </div>
              <span className="weight-ok">Total Maximum Score: {displayWeight(assignmentData.total_active_weight)}</span>
            </div>

            <label className="field">
              <span>Agent</span>
              <select value={selectedUserId} onChange={handleUserChange}>
                <option value="">Select agent</option>
                {agentUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name} - {user.email}</option>)}
              </select>
            </label>

            {selectedUserId ? (
              <>
                <div className="assignment-summary-grid">
                  <div>
                    <span>Current task</span>
                    <strong>{currentAssignmentGroup?.categoryName || 'No task assigned'}</strong>
                  </div>
                  <div>
                    <span>Current subtasks</span>
                    <strong>{currentAssignments.length}</strong>
                  </div>
                  <div>
                    <span>Included subtasks</span>
                    <strong>{currentAssignmentGroup?.assignments.length || 0}</strong>
                  </div>
                </div>

                {assignmentGroupsByCategory.length === 0 ? <p className="field-help">No task assigned to this agent yet.</p> : null}
                {assignmentGroupsByCategory.map((group) => (
                  <div className="assigned-task-group" key={group.categoryName}>
                    <div className="assigned-task-group-header">
                      <strong>{group.categoryName}</strong>
                    </div>
                    <div className="table-scroll">
                      <table className="users-table task-assignment-table">
                        <thead>
                          <tr>
                            <th>Subtask</th>
                            <th>Source</th>
                            <th>Weight</th>
                            <th>Dates</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.assignments.map((assignment) => (
                            <tr key={assignment.id}>
                              <td>{assignment.subtask_name}</td>
                              <td>{sourceLabel(assignment.source_type)}</td>
                              <td>{displayWeight(assignment.quality_weight)}</td>
                              <td>{assignment.effective_from}{assignment.effective_to ? ` to ${assignment.effective_to}` : ''}</td>
                              <td>{labelize(assignment.status)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}

                <h3 className="task-assignment-subheading">{assigningTaskId ? 'Replace Main Task' : 'Assign a Main Task'}</h3>
                {!assigningTaskId ? (
                  <div className="task-picker-list">
                    {categories.filter((category) => category.status === 'ACTIVE').map((category) => (
                      <button className="task-picker-item" type="button" key={category.id} onClick={() => startTaskAssignment(category.id)}>
                        <span>
                          <strong>{category.name}</strong>
                          <small>{(category.subtasks || []).filter((subtask) => subtask.status === 'ACTIVE').length} active subtasks</small>
                        </span>
                        <Icon name="chevron" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <form className="management-form task-assignment-form" onSubmit={submitTaskAssignment}>
                    <p className="field-help">Assigning <strong>{assignmentCategory?.name}</strong> automatically assigns every active subtask below. Set each subtask's maximum score and confirm the effective dates.</p>
                    {assignableSubtasksForForm.map((subtask) => (
                      <label className="field task-weight-field" key={subtask.id}>
                        <span>
                          {subtask.name}
                          <small>({sourceLabel(subtask.source_type)} · Maximum Score){assignedSubtaskIdsForUser.has(subtask.id) ? ' · already active' : ''}</small>
                        </span>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={subtaskWeights[subtask.id] ?? 0}
                          onChange={(event) => setSubtaskWeights((current) => ({ ...current, [subtask.id]: event.target.value }))}
                        />
                      </label>
                    ))}
                    <div className="pms-form-row">
                      <label className="field">
                        <span>Effective From</span>
                        <input type="date" value={taskAssignmentForm.effective_from} onChange={(event) => setTaskAssignmentForm((current) => ({ ...current, effective_from: event.target.value }))} required />
                      </label>
                      <label className="field">
                        <span>Effective To</span>
                        <input type="date" value={taskAssignmentForm.effective_to || ''} onChange={(event) => setTaskAssignmentForm((current) => ({ ...current, effective_to: event.target.value }))} />
                      </label>
                    </div>
                    <div className="pms-form-row">
                      <label className="field">
                        <span>Status</span>
                        <select value={taskAssignmentForm.status} onChange={(event) => setTaskAssignmentForm((current) => ({ ...current, status: event.target.value }))}>
                          {STATUSES.map((item) => <option key={item}>{item}</option>)}
                        </select>
                      </label>
                    </div>
                    <label className="checkbox-field">
                      <input type="checkbox" checked={taskAssignmentForm.auto_fetch_enabled} onChange={(event) => setTaskAssignmentForm((current) => ({ ...current, auto_fetch_enabled: event.target.checked }))} />
                      Auto fetch enabled for automatic subtasks
                    </label>
                    <div className="pms-form-row">
                      <button className="primary-button compact-action" type="submit">Assign Task to Agent</button>
                      <button className="secondary-button compact-action" type="button" onClick={cancelTaskAssignment}>Cancel</button>
                    </div>
                  </form>
                )}
              </>
            ) : <p className="field-help">Select an agent to view or assign their current task.</p>}
          </section>
        </section>
      </main>
    </AppLayout>
  )
}
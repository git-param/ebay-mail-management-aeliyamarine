import { Fragment, useEffect, useMemo, useRef, useState } from 'react'

import AppLayout, { Icon } from '../../layouts/app_layout'
import { deleteSubSubtask, deleteSubtask, deleteTaskCategory, fetchTaskCategories, fetchUserTaskAssignments, saveSubSubtask, saveSubtask, saveTaskAssignment, saveTaskCategory } from '../../services/taskManagementApi'
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

function emptySubSubtask(subtaskId = '') {
  return {
    subtask_id: subtaskId,
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

function subSubtaskSummaryForm(child) {
  return {
    subtask_id: child.subtask_id,
    name: child.name,
    description: child.description || '',
    status: child.status,
    source_type: child.source_type,
    source_reference_id: child.source_reference_id || '',
    source_configuration: child.source_configuration || null,
    count_method: child.count_method || '',
    completion_rule: child.completion_rule || '',
  }
}

function assignmentSubtasks(category) {
  return (category?.subtasks || [])
    .filter((subtask) => subtask.status === 'ACTIVE')
    .map((subtask) => ({
      key: subtask.id,
      id: subtask.id,
      name: subtask.name,
      source_type: subtask.source_type,
      child_count: (subtask.child_tasks || []).filter((child) => child.status === 'ACTIVE').length,
    }))
}

export default function TaskManagement({ currentUser, onLogout }) {
  const [categories, setCategories] = useState([])
  const [users, setUsers] = useState([])
  const [messageTypes, setMessageTypes] = useState([])
  const [selectedCategoryId, setSelectedCategoryId] = useState('')
  const [categoryForm, setCategoryForm] = useState(emptyCategory())
  const [subtaskForm, setSubtaskForm] = useState(emptySubtask())
  const [subSubtaskForm, setSubSubtaskForm] = useState(emptySubSubtask())
  const [selectedUserId, setSelectedUserId] = useState('')
  const [assignmentData, setAssignmentData] = useState({ total_active_weight: 0, assignments: [] })
  const [taskAssignmentForm, setTaskAssignmentForm] = useState(emptyTaskAssignment())
  const [subtaskWeights, setSubtaskWeights] = useState({})
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [editingSubtaskId, setEditingSubtaskId] = useState('')
  const [editingSubSubtaskId, setEditingSubSubtaskId] = useState('')
  const [assigningTaskId, setAssigningTaskId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [pageView, setPageView] = useState('tasks')
  const [workspaceTab, setWorkspaceTab] = useState('subtasks')
  const [subtaskEditor, setSubtaskEditor] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [loading, setLoading] = useState(true)
  const editorNameRef = useRef(null)

  useEffect(() => {
    if (pageView === 'workspace' && (workspaceTab === 'details' || subtaskEditor)) {
      editorNameRef.current?.focus()
    }
  }, [pageView, workspaceTab, subtaskEditor, editingSubtaskId, editingSubSubtaskId])

  const visibleCategories = categories.filter((category) =>
    (statusFilter === 'ALL' || category.status === statusFilter)
    && `${category.name} ${category.description || ''}`.toLowerCase().includes(search.toLowerCase()),
  )

  const selectedCategory = useMemo(() => categories.find((item) => item.id === selectedCategoryId) || null, [categories, selectedCategoryId])
  const activeMessageTypes = useMemo(() => flattenMessageTypes(messageTypes).filter((item) => item.is_active && !item.is_deleted), [messageTypes])
  const agentUsers = users.filter((user) => normalizeRole(user.role) === 'AGENT' && user.is_active !== false)
  const displayWeight = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })

  const currentAssignments = useMemo(() => assignmentData.assignments || [], [assignmentData.assignments])
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
  const assignableSubtasksForForm = useMemo(() => assignmentSubtasks(assignmentCategory), [assignmentCategory])

  async function load() {
    try {
      const [categoryData, userData, messageTypeData] = await Promise.all([fetchTaskCategories(), fetchUsers(), fetchMessageTypes(false)])
      setCategories(categoryData || [])
      setUsers(userData.items || userData || [])
      setMessageTypes(messageTypeData || [])
      setError('')
    } catch (caught) {
      setError(caught.message)
    } finally {
      setLoading(false)
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

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchTaskCategories(), fetchUsers(), fetchMessageTypes(false)])
      .then(([categoryData, userData, messageTypeData]) => {
        if (cancelled) return
        setCategories(categoryData || [])
        setUsers(userData.items || userData || [])
        setMessageTypes(messageTypeData || [])
        setError('')
      })
      .catch((caught) => { if (!cancelled) setError(caught.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  function createNewTask() {
    setPageView('workspace')
    setWorkspaceTab('details')
    setSubtaskEditor('')
    setSelectedCategoryId('')
    setEditingCategoryId('')
    setCategoryForm(emptyCategory())
    setEditingSubtaskId('')
    setSubtaskForm(emptySubtask())
    setEditingSubSubtaskId('')
    setSubSubtaskForm(emptySubSubtask())
  }

  function openTask(category) {
    if (!category) {
      createNewTask()
      return
    }
    setPageView('workspace')
    setWorkspaceTab('subtasks')
    setSubtaskEditor('')
    setSelectedCategoryId(category.id)
    setEditingCategoryId(category.id)
    setCategoryForm(taskSummaryForm(category))
    setEditingSubtaskId('')
    setSubtaskForm(emptySubtask(category.id))
    setEditingSubSubtaskId('')
    setSubSubtaskForm(emptySubSubtask((category.subtasks || [])[0]?.id || ''))
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
      setWorkspaceTab('subtasks')
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
        setPageView('tasks')
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
      setEditingSubSubtaskId('')
      setSubSubtaskForm(emptySubSubtask(''))
      setSubtaskEditor('')
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
      if (subSubtaskForm.subtask_id === subtask.id) {
        setEditingSubSubtaskId('')
        setSubSubtaskForm(emptySubSubtask(''))
      }
      await load()
      setMessage('Subtask deleted.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  function editSubtask(subtask) {
    setSubtaskEditor('subtask')
    setSelectedCategoryId(subtask.task_category_id)
    setEditingSubtaskId(subtask.id)
    setSubtaskForm(subtaskSummaryForm(subtask))
  }

  async function submitSubSubtask(event) {
    event.preventDefault()
    try {
      setError('')
      setMessage('')
      if (subSubtaskForm.source_type === 'MESSAGE_TYPE' && !subSubtaskForm.source_reference_id) {
        setError('Select a Message Type for this sub-subtask.')
        return
      }
      if (!subSubtaskForm.subtask_id) {
        setError('Select a parent subtask before adding a sub-subtask.')
        return
      }
      const payload = {
        ...subSubtaskForm,
        source_reference_id: subSubtaskForm.source_type === 'MESSAGE_TYPE' ? (subSubtaskForm.source_reference_id || null) : null,
        source_configuration: subSubtaskForm.source_configuration || null,
      }
      await saveSubSubtask(payload, editingSubSubtaskId)
      await load()
      setEditingSubSubtaskId('')
      setSubSubtaskForm(emptySubSubtask(subSubtaskForm.subtask_id))
      setSubtaskEditor('')
      setMessage('Sub-subtask saved.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  async function deleteSubSubtaskItem(child) {
    if (!child) return
    if (!window.confirm(`Delete sub-subtask "${child.name}"?`)) return
    try {
      setError('')
      setMessage('')
      await deleteSubSubtask(child.id)
      if (editingSubSubtaskId === child.id) {
        setEditingSubSubtaskId('')
        setSubSubtaskForm(emptySubSubtask(child.subtask_id))
      }
      await load()
      setMessage('Sub-subtask deleted.')
    } catch (caught) {
      setError(caught.message)
    }
  }

  function editSubSubtask(child) {
    setSubtaskEditor('child')
    const parent = (selectedCategory?.subtasks || []).find((subtask) => subtask.id === child.subtask_id)
    if (parent) {
      setSelectedCategoryId(parent.task_category_id)
    }
    setEditingSubSubtaskId(child.id)
    setSubSubtaskForm(subSubtaskSummaryForm(child))
  }

  function startTaskAssignment(categoryId) {
    const category = categories.find((item) => item.id === categoryId)
    const initialWeights = {}
    for (const subtask of assignmentSubtasks(category)) {
      const existingWeight = currentAssignments
        .filter((item) => item.subtask_id === subtask.id)
        .reduce((total, item) => total + Number(item.quality_weight || 0), 0)
      initialWeights[subtask.id] = existingWeight
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

  return (
    <AppLayout activePage="Task Management" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page task-management-page">
        <div className="page-header">
          <div>
            <h1>Task Management</h1>
            <p>Organize your team's work and manage agent scores.</p>
          </div>
          <div className="task-header-actions">
            <button className="secondary-button compact-action" type="button" onClick={() => { setLoading(true); load() }} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
            <button className="primary-button compact-action" type="button" onClick={createNewTask}>+ New Task</button>
          </div>
        </div>

        <nav className="task-page-navigation" aria-label="Task management sections">
          <button type="button" className={pageView !== 'assignments' ? 'is-active' : ''} aria-current={pageView !== 'assignments' ? 'page' : undefined} onClick={() => setPageView('tasks')}>Tasks <span>{categories.length}</span></button>
          <button type="button" className={pageView === 'assignments' ? 'is-active' : ''} aria-current={pageView === 'assignments' ? 'page' : undefined} onClick={() => setPageView('assignments')}>Agent Assignments</button>
        </nav>

        {error ? <p className="form-message error" role="alert">{error}</p> : null}
        {message ? <p className="form-message success" role="status">{message}</p> : null}

        {pageView === 'tasks' ? (
          <section className="task-overview" aria-label="Tasks">
            <div className="task-overview-toolbar">
              <div><h2>Your tasks</h2><p className="task-section-note">Open a card to manage its details and subtasks.</p></div>
              <div className="task-overview-filters">
                <label className="field"><span className="task-visually-hidden">Search tasks</span><input type="search" placeholder="Search tasks…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
                <label className="field"><span className="task-visually-hidden">Filter by status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All statuses</option>{STATUSES.map((status) => <option key={status} value={status}>{labelize(status)}</option>)}</select></label>
              </div>
            </div>
            {loading && !categories.length ? <div className="task-overview-empty" role="status">Loading tasks…</div> : (
              <div className="task-card-grid">
                {visibleCategories.map((category) => {
                  const subtasks = category.subtasks || []
                  const childCount = subtasks.reduce((total, subtask) => total + (subtask.child_tasks || []).length, 0)
                  return (
                    <button className="task-overview-card" type="button" key={category.id} onClick={() => openTask(category)}>
                      <div className="task-card-top"><span className="task-card-icon"><Icon name="audit" /></span><span className={`task-status task-status-${category.status.toLowerCase()}`}>{labelize(category.status)}</span></div>
                      <h3>{category.name}</h3>
                      <p>{category.description || 'Manage the work, subtasks, and sources for this task.'}</p>
                      <div className="task-card-metrics"><span><strong>{subtasks.length}</strong> subtasks</span><span><strong>{childCount}</strong> sub-subtasks</span></div>
                      <div className="task-card-footer"><span>Manage task</span><Icon name="chevron" /></div>
                    </button>
                  )
                })}
                <button className="task-overview-card task-create-card" type="button" onClick={createNewTask}><span className="task-create-symbol" aria-hidden="true">+</span><h3>Create a task</h3><p>Add a new area of work for your team.</p></button>
              </div>
            )}
            {!loading && !visibleCategories.length ? <p className="task-overview-empty">{categories.length ? 'No tasks match your search or status filter.' : 'Create your first task to get started.'}</p> : null}
          </section>
        ) : null}

        {pageView === 'workspace' ? (
          <div className="task-workspace-header">
            <button className="secondary-button compact-action" type="button" onClick={() => setPageView('tasks')}>← All Tasks</button>
            <div><h2>{selectedCategory?.name || 'Create a task'}</h2><p className="task-section-note">{selectedCategory ? 'Manage this task and the work within it.' : 'Give your task a name and description to get started.'}</p></div>
            {selectedCategory ? <nav className="task-workspace-tabs" aria-label="Task views"><button type="button" className={workspaceTab === 'subtasks' ? 'is-active' : ''} aria-current={workspaceTab === 'subtasks' ? 'page' : undefined} onClick={() => setWorkspaceTab('subtasks')}>Subtasks <span>{selectedCategory.subtasks?.length || 0}</span></button><button type="button" className={workspaceTab === 'details' ? 'is-active' : ''} aria-current={workspaceTab === 'details' ? 'page' : undefined} onClick={() => setWorkspaceTab('details')}>Task Details</button></nav> : null}
          </div>
        ) : null}

        <section className="task-management-grid">
          {pageView === 'workspace' && workspaceTab === 'details' ? <section className="table-card task-editor-panel">
            <div className="pms-card-header">
              <div>
                <h2>{selectedCategory ? 'Task Details' : 'New Task'}</h2>
                <p className="task-section-note">{selectedCategory ? 'Update the name, description, and availability of this task.' : 'A default Other subtask is included with every new task.'}</p>
              </div>
              <div className="task-toolbar-actions">
                <button className="danger-button compact-action" type="button" onClick={() => deleteCategory(selectedCategory)} disabled={!selectedCategory} aria-label="Delete task" title="Delete task">
                  <Icon name="trash" />
                </button>
              </div>
            </div>

            <form className="management-form task-management-form" onSubmit={submitCategory}>
              <h3>{editingCategoryId ? 'Edit Task' : 'Create Task'}</h3>
              <label className="field">
                <span>Name</span>
                <input ref={editorNameRef} value={categoryForm.name} onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))} required />
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
          </section> : null}

          {pageView === 'workspace' && workspaceTab === 'subtasks' && selectedCategory ? <section className="table-card task-subtask-panel">
            <div className="pms-card-header">
              <div>
                <h2>Subtasks</h2>
                <p className="task-section-note">Break this task into smaller pieces of work.</p>
              </div>
              <div className="task-header-actions">
                <button className="secondary-button compact-action" type="button" disabled={!selectedCategory.subtasks?.length} onClick={() => { setEditingSubSubtaskId(''); setSubSubtaskForm(emptySubSubtask(selectedCategory.subtasks?.[0]?.id || '')); setSubtaskEditor('child') }}>+ Sub-Subtask</button>
                <button className="primary-button compact-action" type="button" onClick={() => { setEditingSubtaskId(''); setSubtaskForm(emptySubtask(selectedCategoryId)); setSubtaskEditor('subtask') }}>+ Add Subtask</button>
              </div>
            </div>

            <div className="task-table-scroll" role="region" aria-label="Subtasks table" tabIndex="0">
              <table className="task-subtask-table">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Source</th>
                    <th scope="col">Status</th>
                    <th scope="col">Assignments</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedCategory?.subtasks || []).map((subtask) => (
                    <Fragment key={subtask.id}>
                      <tr>
                      <td data-label="Name">
                        <strong>{subtask.name}</strong>
                        {subtask.name.toLowerCase() === 'other' ? <div className="row-meta">Default catch-all subtask</div> : null}
                      </td>
                      <td data-label="Source">
                        {sourceLabel(subtask.source_type)}
                        {subtask.source_type === 'MESSAGE_TYPE' ? ` · ${activeMessageTypes.find((item) => item.id === subtask.source_reference_id)?.name || 'Unknown'}` : ''}
                      </td>
                      <td data-label="Status"><span className={`task-status task-status-${subtask.status.toLowerCase()}`}>{labelize(subtask.status)}</span></td>
                      <td data-label="Assignments">{subtask.assignment_count}</td>
                      <td data-label="Actions">
                        <div className="row-actions">
                          <button className="icon-button" type="button" onClick={() => editSubtask(subtask)} title="Edit subtask"><Icon name="edit" /></button>
                          <button className="icon-button danger-icon" type="button" onClick={() => deleteSubtaskItem(subtask)} title="Delete subtask"><Icon name="trash" /></button>
                        </div>
                      </td>
                      </tr>
                      {(subtask.child_tasks || []).map((child) => (
                        <tr className="sub-subtask-row" key={child.id}>
                          <td data-label="Name">
                            <strong>{child.name}</strong>
                            <div className="row-meta">Under {subtask.name}</div>
                          </td>
                          <td data-label="Source">
                            {sourceLabel(child.source_type)}
                            {child.source_type === 'MESSAGE_TYPE' ? ` - ${activeMessageTypes.find((item) => item.id === child.source_reference_id)?.name || 'Unknown'}` : ''}
                          </td>
                          <td data-label="Status"><span className={`task-status task-status-${child.status.toLowerCase()}`}>{labelize(child.status)}</span></td>
                          <td data-label="Assignments">{child.assignment_count}</td>
                          <td data-label="Actions">
                            <div className="row-actions">
                              <button className="icon-button" type="button" onClick={() => editSubSubtask(child)} title="Edit sub-subtask"><Icon name="edit" /></button>
                              <button className="icon-button danger-icon" type="button" onClick={() => deleteSubSubtaskItem(child)} title="Delete sub-subtask"><Icon name="trash" /></button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                  {!selectedCategory?.subtasks?.length ? (
                    <tr><td className="task-subtask-empty" colSpan={5}>{selectedCategory ? 'No subtasks yet. Add a subtask below to get started.' : 'Select a task to view its subtasks.'}</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {subtaskEditor === 'subtask' ? <form className="management-form task-subtask-form" onSubmit={submitSubtask}>
              <h3>{editingSubtaskId ? 'Edit Subtask' : 'Add Subtask'}</h3>
              <label className="field">
                <span>Name</span>
                <input ref={editorNameRef} value={subtaskForm.name} onChange={(event) => setSubtaskForm((current) => ({ ...current, name: event.target.value }))} required />
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
              <button className="secondary-button compact-action" type="button" onClick={() => setSubtaskEditor('')}>Cancel</button>
            </form> : null}

            {subtaskEditor === 'child' ? <form className="management-form task-subtask-form task-child-form" onSubmit={submitSubSubtask}>
              <h3>{editingSubSubtaskId ? 'Edit Sub-Subtask' : 'Add Sub-Subtask'}</h3>
              <label className="field">
                <span>Parent Subtask</span>
                <select value={subSubtaskForm.subtask_id} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, subtask_id: event.target.value }))} required disabled={Boolean(editingSubSubtaskId)}>
                  <option value="">Select subtask</option>
                  {(selectedCategory?.subtasks || []).map((subtask) => <option key={subtask.id} value={subtask.id}>{subtask.name}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Name</span>
                <input ref={editorNameRef} value={subSubtaskForm.name} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, name: event.target.value }))} required />
              </label>
              <div className="pms-form-row">
                <label className="field">
                  <span>Source</span>
                  <select value={subSubtaskForm.source_type} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, source_type: event.target.value, source_reference_id: event.target.value === 'MESSAGE_TYPE' ? current.source_reference_id : '' }))}>
                    {SOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Status</span>
                  <select value={subSubtaskForm.status} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, status: event.target.value }))}>
                    {STATUSES.map((item) => <option key={item}>{item}</option>)}
                  </select>
                </label>
              </div>
              {subSubtaskForm.source_type === 'MESSAGE_TYPE' ? (
                <label className="field">
                  <span>Message Type</span>
                  <select value={subSubtaskForm.source_reference_id} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, source_reference_id: event.target.value }))} required>
                    <option value="">Select message type</option>
                    {activeMessageTypes.map((item) => <option key={item.id} value={item.id}>{'  '.repeat(item.depth)}{item.name}</option>)}
                  </select>
                </label>
              ) : null}
              <p className="field-help">{AUTO_SOURCE_TYPES.has(subSubtaskForm.source_type) ? 'This sub-subtask will be automatically fetched on Daily Task Entry.' : 'This sub-subtask requires manual score entry on Daily Task Entry.'}</p>
              <label className="field">
                <span>Description</span>
                <textarea value={subSubtaskForm.description || ''} onChange={(event) => setSubSubtaskForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
              <div className="pms-form-row">
                <button className="primary-button compact-action" type="submit">{editingSubSubtaskId ? 'Save Sub-Subtask' : 'Add Sub-Subtask'}</button>
                <button className="secondary-button compact-action" type="button" onClick={() => setSubtaskEditor('')}>Cancel</button>
              </div>
            </form> : null}
          </section> : null}

          {pageView === 'assignments' ? <section className="table-card task-assignment-panel">
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
                    <span>Current items</span>
                    <strong>{currentAssignments.length}</strong>
                  </div>
                  <div>
                    <span>Included items</span>
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
                              <td>{assignment.sub_subtask_name ? `${assignment.subtask_name} - ${assignment.sub_subtask_name}` : assignment.subtask_name}</td>
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
                          <small>{assignmentSubtasks(category).length} active subtasks</small>
                        </span>
                        <Icon name="chevron" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <form className="management-form task-assignment-form" onSubmit={submitTaskAssignment}>
                    <p className="field-help">Assigning <strong>{assignmentCategory?.name}</strong> shows subtasks only. If a subtask has sub-subtasks, its maximum score is split equally between them.</p>
                    {assignableSubtasksForForm.map((subtask) => (
                      <label className="field task-weight-field" key={subtask.id}>
                        <span>
                          {subtask.name}
                          <small>
                            {subtask.child_count ? `${subtask.child_count} sub-subtasks - ` : ''}
                            {sourceLabel(subtask.source_type)} - Maximum Score
                          </small>
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
                      Auto fetch enabled for automatic items
                    </label>
                    <div className="pms-form-row">
                      <button className="primary-button compact-action" type="submit">Assign Task to Agent</button>
                      <button className="secondary-button compact-action" type="button" onClick={cancelTaskAssignment}>Cancel</button>
                    </div>
                  </form>
                )}
              </>
            ) : <p className="field-help">Select an agent to view or assign their current task.</p>}
          </section> : null}
        </section>
      </main>
    </AppLayout>
  )
}

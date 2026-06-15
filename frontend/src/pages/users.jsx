import { useEffect, useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import {
  activateUser,
  createUser,
  deactivateUser,
  fetchUser,
  fetchUsers,
  resetUserPassword,
  updateUser,
} from '../services/userApi'

const ROLES = ['Admin', 'Operations Manager', 'Agent']
const STATUSES = ['Active', 'Inactive']

const EMPTY_FORM = {
  fullName: '',
  email: '',
  role: 'Agent',
  status: 'Active',
  password: '',
  confirmPassword: '',
}

function getInitials(name) {
  if (!name) {
    return 'U'
  }

  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function formatDate(value) {
  if (!value) {
    return 'Not available'
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

function formatRole(role) {
  const normalizedRole = String(role || '')
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, '_')

  const labels = {
    ADMIN: 'Admin',
    OPS_MANAGER: 'Operations Manager',
    OPERATIONS_MANAGER: 'Operations Manager',
    AGENT: 'Agent',
    SUPPORT_AGENT: 'Agent',
  }

  return labels[normalizedRole] || role || 'Agent'
}

function normalizeUser(user) {
  const isActive = typeof user.is_active === 'boolean' ? user.is_active : user.status !== 'Inactive'

  return {
    ...user,
    id: user.id || user.user_id,
    fullName: user.name || user.full_name || user.fullName || '',
    email: user.email || '',
    role: formatRole(user.role),
    status: isActive ? 'Active' : 'Inactive',
    createdDate: formatDate(user.created_at || user.createdDate || user.created_date),
    lastLogin: formatDate(user.last_login || user.lastLogin || user.last_login_at),
    assignedConversations: user.assigned_conversations || user.assignedConversations || 0,
    assignedCategories: user.assigned_categories || user.assignedCategories || [],
    activities: user.recent_activities || user.activities || [],
    raw: user,
  }
}

function getUsersFromResponse(response) {
  if (Array.isArray(response)) {
    return response
  }

  if (Array.isArray(response.data)) {
    return response.data
  }

  if (response.data && Array.isArray(response.data.users)) {
    return response.data.users
  }

  return response.users || response.items || []
}

function toUserPayload(values) {
  return {
    name: values.fullName.trim(),
    email: values.email.trim(),
    role: values.role,
    is_active: values.status === 'Active',
    ...(values.password ? { password: values.password } : {}),
  }
}

function StatCard({ label, value }) {
  return (
    <article className="stat-card">
      <span className="stat-icon">
        <Icon name="users" />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  )
}

function Badge({ type, value }) {
  const className = `${type}-badge ${type}-${value.toLowerCase().replace(/\s+/g, '-')}`
  return <span className={className}>{value}</span>
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

function UserForm({ mode, initialValues, isSubmitting, onCancel, onSubmit }) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})

  function updateField(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = {}

    if (!values.fullName.trim()) {
      nextErrors.fullName = 'Full name is required.'
    }
    if (!values.email.trim()) {
      nextErrors.email = 'Email is required.'
    } else if (!validateEmail(values.email)) {
      nextErrors.email = 'Enter a valid email address.'
    }
    if (mode === 'create') {
      if (!values.password) {
        nextErrors.password = 'Password is required.'
      }
      if (!values.confirmPassword) {
        nextErrors.confirmPassword = 'Confirm password is required.'
      } else if (values.password !== values.confirmPassword) {
        nextErrors.confirmPassword = 'Passwords do not match.'
      }
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
        <span>Full Name</span>
        <input name="fullName" value={values.fullName} onChange={updateField} />
        {errors.fullName ? <small>{errors.fullName}</small> : null}
      </label>

      <label className="field">
        <span>Email</span>
        <input name="email" type="email" value={values.email} onChange={updateField} />
        {errors.email ? <small>{errors.email}</small> : null}
      </label>

      <label className="field">
        <span>Role</span>
        <select name="role" value={values.role} onChange={updateField}>
          {ROLES.map((role) => (
            <option value={role} key={role}>
              {role}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Status</span>
        <select name="status" value={values.status} onChange={updateField}>
          {STATUSES.map((status) => (
            <option value={status} key={status}>
              {status}
            </option>
          ))}
        </select>
      </label>

      {mode === 'create' ? (
        <>
          <label className="field">
            <span>Password</span>
            <input name="password" type="password" value={values.password} onChange={updateField} />
            {errors.password ? <small>{errors.password}</small> : null}
          </label>

          <label className="field">
            <span>Confirm Password</span>
            <input name="confirmPassword" type="password" value={values.confirmPassword} onChange={updateField} />
            {errors.confirmPassword ? <small>{errors.confirmPassword}</small> : null}
          </label>
        </>
      ) : null}

      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="primary-button compact" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving...' : mode === 'create' ? 'Create User' : 'Save Changes'}
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

function UserDrawer({ user, onClose }) {
  if (!user) {
    return null
  }

  const knownFields = new Set([
    'id',
    'user_id',
    'name',
    'full_name',
    'fullName',
    'email',
    'role',
    'status',
    'is_active',
    'created_at',
    'createdDate',
    'created_date',
    'last_login',
    'lastLogin',
    'last_login_at',
    'assigned_conversations',
    'assignedConversations',
    'assigned_categories',
    'assignedCategories',
    'recent_activities',
    'activities',
    'password_hash',
    'raw',
  ])
  const additionalFields = Object.entries(user.raw || {}).filter(([key, value]) => {
    return !knownFields.has(key) && value !== null && value !== undefined && typeof value !== 'object'
  })

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="user-drawer" aria-labelledby="drawer-title">
        <div className="drawer-header">
          <h2 id="drawer-title">User Details</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close details">
            x
          </button>
        </div>

        <div className="drawer-profile">
          <span className="avatar large">{getInitials(user.fullName)}</span>
          <h3>{user.fullName}</h3>
          <p>{user.email}</p>
          <div className="badge-row">
            <Badge type="role" value={user.role} />
            <Badge type="status" value={user.status} />
          </div>
        </div>

        <dl className="detail-grid">
          <div>
            <dt>Created Date</dt>
            <dd>{user.createdDate}</dd>
          </div>
          <div>
            <dt>Last Login</dt>
            <dd>{user.lastLogin}</dd>
          </div>
          <div>
            <dt>Assigned Conversations</dt>
            <dd>{user.assignedConversations}</dd>
          </div>
        </dl>

        {user.assignedCategories.length ? (
          <section className="drawer-section">
            <h3>Assigned Categories</h3>
            <div className="category-list">
              {user.assignedCategories.map((category) => (
                <span key={category}>{category}</span>
              ))}
            </div>
          </section>
        ) : null}

        {user.activities.length ? (
          <section className="drawer-section">
            <h3>Recent Activities</h3>
            <ul className="activity-list">
              {user.activities.map((activity) => (
                <li key={activity}>{activity}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {additionalFields.length ? (
          <section className="drawer-section">
            <h3>Additional Details</h3>
            <dl className="detail-grid">
              {additionalFields.map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replace(/_/g, ' ')}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}
      </aside>
    </div>
  )
}

function Users({ currentUser, onLogout }) {
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('All Roles')
  const [statusFilter, setStatusFilter] = useState('All')
  const [actionUserId, setActionUserId] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function loadUsers() {
    setIsLoading(true)
    setError('')

    try {
      const response = await fetchUsers()
      setUsers(getUsersFromResponse(response).map(normalizeUser))
    } catch (caughtError) {
      setError(caughtError.message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const query = search.trim().toLowerCase()
      const matchesSearch =
        !query || user.fullName.toLowerCase().includes(query) || user.email.toLowerCase().includes(query)
      const matchesRole = roleFilter === 'All Roles' || user.role === roleFilter
      const matchesStatus = statusFilter === 'All' || user.status === statusFilter
      return matchesSearch && matchesRole && matchesStatus
    })
  }, [users, search, roleFilter, statusFilter])

  const stats = useMemo(
    () => ({
      total: users.length,
      active: users.filter((user) => user.status === 'Active').length,
      agents: users.filter((user) => user.role === 'Agent').length,
      managers: users.filter((user) => user.role === 'Operations Manager').length,
    }),
    [users],
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

  function openModal(type, user = null) {
    setActionUserId(null)
    setSelectedUser(user)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedUser(null)
  }

  async function createUserFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await createUser(toUserPayload(values))
      closeModal()
      showNotification('User created successfully.')
      await loadUsers()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function updateUserFromForm(values) {
    setIsSubmitting(true)
    setError('')

    try {
      await updateUser(selectedUser.id, toUserPayload(values))
      closeModal()
      showNotification('User updated successfully.')
      await loadUsers()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function setUserStatus(user, status) {
    setIsSubmitting(true)
    setError('')

    try {
      if (status === 'Active') {
        await activateUser(user.id)
      } else {
        await deactivateUser(user.id)
      }
      closeModal()
      showNotification(status === 'Active' ? 'User activated successfully.' : 'User disabled successfully.')
      await loadUsers()
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function resetPassword() {
    setIsSubmitting(true)
    setError('')

    try {
      await resetUserPassword(selectedUser.id)
      closeModal()
      showNotification('Password reset notification sent.')
    } catch (caughtError) {
      showError(caughtError)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function viewUser(user) {
    setActionUserId(null)
    setError('')

    try {
      const response = await fetchUser(user.id)
      setSelectedUser(normalizeUser(response))
    } catch (caughtError) {
      showError(caughtError)
    }
  }

  function resetFilters() {
    setSearch('')
    setRoleFilter('All Roles')
    setStatusFilter('All')
  }

  return (
    <AppLayout activePage="Users" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Users</h1>
            <p>Manage platform users and permissions</p>
          </div>
          <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
            <Icon name="plus" />
            Create User
          </button>
        </div>

        <section className="stats-grid" aria-label="User summary">
          <StatCard label="Total Users" value={stats.total} />
          <StatCard label="Active Users" value={stats.active} />
          <StatCard label="Agents" value={stats.agents} />
          <StatCard label="Operations Managers" value={stats.managers} />
        </section>

        <section className="filter-panel" aria-label="User filters">
          <label className="field search-field">
            <span>Search</span>
            <input
              type="search"
              placeholder="Search by name or email"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Role</span>
            <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
              <option>All Roles</option>
              {ROLES.map((role) => (
                <option key={role}>{role}</option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option>All</option>
              {STATUSES.map((status) => (
                <option key={status}>{status}</option>
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

        <section className="table-card" aria-label="Users table">
          {isLoading ? (
            <div className="empty-state">
              <h2>Loading users...</h2>
            </div>
          ) : filteredUsers.length ? (
            <div className="table-scroll">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>Avatar</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created Date</th>
                    <th>Last Login</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <span className="avatar">{getInitials(user.fullName)}</span>
                      </td>
                      <td>
                        <strong>{user.fullName}</strong>
                      </td>
                      <td>{user.email}</td>
                      <td>
                        <Badge type="role" value={user.role} />
                      </td>
                      <td>
                        <Badge type="status" value={user.status} />
                      </td>
                      <td>{user.createdDate}</td>
                      <td>{user.lastLogin}</td>
                      <td className="actions-cell">
                        <button
                          className="icon-button"
                          type="button"
                          onClick={() => setActionUserId((current) => (current === user.id ? null : user.id))}
                          aria-label={`Open actions for ${user.fullName}`}
                        >
                          <Icon name="dots" />
                        </button>
                        {actionUserId === user.id ? (
                          <div className="action-menu">
                            <button
                              className="menu-view"
                              type="button"
                              onClick={() => viewUser(user)}
                            >
                              <Icon name="eye" />
                              View User
                            </button>
                            <button className="menu-edit" type="button" onClick={() => openModal('edit', user)}>
                              <Icon name="edit" />
                              Edit User
                            </button>
                            <button className="menu-reset" type="button" onClick={() => openModal('reset', user)}>
                              <Icon name="key" />
                              Reset Password
                            </button>
                            {user.status === 'Active' ? (
                              <button
                                className="menu-disable"
                                type="button"
                                onClick={() => openModal('disable', user)}
                                disabled={isSubmitting}
                              >
                                <Icon name="disable" />
                                Disable User
                              </button>
                            ) : (
                              <button
                                className="menu-activate"
                                type="button"
                                onClick={() => setUserStatus(user, 'Active')}
                                disabled={isSubmitting}
                              >
                                <Icon name="activate" />
                                Activate User
                              </button>
                            )}
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
              <h2>No users found</h2>
              <button className="primary-button compact" type="button" onClick={() => openModal('create')}>
                Create User
              </button>
            </div>
          )}
        </section>
      </main>

      {notification ? <div className="toast">{notification}</div> : null}

      {modal === 'create' ? (
        <Modal title="Create User" onClose={closeModal}>
          <UserForm
            mode="create"
            initialValues={EMPTY_FORM}
            isSubmitting={isSubmitting}
            onCancel={closeModal}
            onSubmit={createUserFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'edit' && selectedUser ? (
        <Modal title="Edit User" onClose={closeModal}>
          <UserForm
            mode="edit"
            initialValues={{
              fullName: selectedUser.fullName,
              email: selectedUser.email,
              role: selectedUser.role,
              status: selectedUser.status,
            }}
            isSubmitting={isSubmitting}
            onCancel={closeModal}
            onSubmit={updateUserFromForm}
          />
        </Modal>
      ) : null}

      {modal === 'reset' && selectedUser ? (
        <ConfirmModal
          title="Reset Password"
          message="Are you sure you want to reset this user's password?"
          actionLabel="Reset Password"
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={resetPassword}
        />
      ) : null}

      {modal === 'disable' && selectedUser ? (
        <ConfirmModal
          title="Disable User"
          message={`Disable ${selectedUser.fullName}'s account? They will no longer be able to access Omni-Desk.`}
          actionLabel="Disable User"
          danger
          isSubmitting={isSubmitting}
          onCancel={closeModal}
          onConfirm={() => setUserStatus(selectedUser, 'Inactive')}
        />
      ) : null}

      <UserDrawer user={selectedUser && !modal ? selectedUser : null} onClose={() => setSelectedUser(null)} />
    </AppLayout>
  )
}

export default Users

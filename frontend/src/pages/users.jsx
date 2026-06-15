import { useMemo, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'

const ROLES = ['Admin', 'Operations Manager', 'Agent']
const STATUSES = ['Active', 'Inactive']

const INITIAL_USERS = [
  {
    id: 1,
    fullName: 'Anika Shah',
    email: 'anika.shah@omnidesk.com',
    role: 'Admin',
    status: 'Active',
    createdDate: 'Jan 08, 2026',
    lastLogin: 'Jun 14, 2026, 09:42 AM',
    assignedConversations: 18,
    assignedCategories: ['Returns', 'Escalations', 'Billing'],
    activities: ['Updated billing template', 'Reviewed audit log', 'Created Agent account'],
  },
  {
    id: 2,
    fullName: 'Marcus Reed',
    email: 'marcus.reed@omnidesk.com',
    role: 'Admin',
    status: 'Active',
    createdDate: 'Jan 12, 2026',
    lastLogin: 'Jun 13, 2026, 05:15 PM',
    assignedConversations: 9,
    assignedCategories: ['System Settings', 'eBay Accounts'],
    activities: ['Activated eBay account', 'Changed user role', 'Exported audit report'],
  },
  {
    id: 3,
    fullName: 'Priya Nair',
    email: 'priya.nair@omnidesk.com',
    role: 'Operations Manager',
    status: 'Active',
    createdDate: 'Feb 03, 2026',
    lastLogin: 'Jun 15, 2026, 10:08 AM',
    assignedConversations: 34,
    assignedCategories: ['Shipping', 'Returns', 'Order Status'],
    activities: ['Assigned 12 conversations', 'Created return category', 'Reviewed SLA queue'],
  },
  {
    id: 4,
    fullName: 'Ethan Brooks',
    email: 'ethan.brooks@omnidesk.com',
    role: 'Operations Manager',
    status: 'Inactive',
    createdDate: 'Feb 17, 2026',
    lastLogin: 'May 29, 2026, 03:22 PM',
    assignedConversations: 11,
    assignedCategories: ['Refunds', 'Feedback'],
    activities: ['Disabled agent account', 'Updated refund workflow', 'Reviewed queue health'],
  },
  {
    id: 5,
    fullName: 'Sofia Martinez',
    email: 'sofia.martinez@omnidesk.com',
    role: 'Agent',
    status: 'Active',
    createdDate: 'Mar 01, 2026',
    lastLogin: 'Jun 15, 2026, 08:51 AM',
    assignedConversations: 42,
    assignedCategories: ['Returns', 'Product Questions'],
    activities: ['Resolved buyer return', 'Sent saved reply', 'Tagged urgent case'],
  },
  {
    id: 6,
    fullName: 'Noah Wilson',
    email: 'noah.wilson@omnidesk.com',
    role: 'Agent',
    status: 'Active',
    createdDate: 'Mar 07, 2026',
    lastLogin: 'Jun 14, 2026, 01:36 PM',
    assignedConversations: 27,
    assignedCategories: ['Shipping', 'Tracking'],
    activities: ['Updated shipping case', 'Merged duplicate thread', 'Added private note'],
  },
  {
    id: 7,
    fullName: 'Isha Patel',
    email: 'isha.patel@omnidesk.com',
    role: 'Agent',
    status: 'Active',
    createdDate: 'Apr 09, 2026',
    lastLogin: 'Jun 15, 2026, 11:02 AM',
    assignedConversations: 39,
    assignedCategories: ['Billing', 'Refunds'],
    activities: ['Processed refund question', 'Escalated payment issue', 'Closed billing thread'],
  },
  {
    id: 8,
    fullName: 'Liam Chen',
    email: 'liam.chen@omnidesk.com',
    role: 'Agent',
    status: 'Inactive',
    createdDate: 'Apr 21, 2026',
    lastLogin: 'Jun 01, 2026, 04:40 PM',
    assignedConversations: 6,
    assignedCategories: ['Feedback', 'Order Status'],
    activities: ['Answered feedback request', 'Updated buyer response', 'Paused assigned queue'],
  },
  {
    id: 9,
    fullName: 'Grace Taylor',
    email: 'grace.taylor@omnidesk.com',
    role: 'Agent',
    status: 'Active',
    createdDate: 'May 02, 2026',
    lastLogin: 'Jun 15, 2026, 09:25 AM',
    assignedConversations: 31,
    assignedCategories: ['Product Questions', 'Shipping'],
    activities: ['Created product macro', 'Reopened buyer thread', 'Resolved tracking issue'],
  },
]

const EMPTY_FORM = {
  fullName: '',
  email: '',
  role: 'Agent',
  status: 'Active',
  password: '',
  confirmPassword: '',
}

function getInitials(name) {
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

function UserForm({ mode, initialValues, onCancel, onSubmit }) {
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
        <button className="primary-button compact" type="submit">
          {mode === 'create' ? 'Create User' : 'Save Changes'}
        </button>
      </div>
    </form>
  )
}

function ConfirmModal({ title, message, actionLabel, danger, onCancel, onConfirm }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="confirm-message">{message}</p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className={danger ? 'danger-button' : 'primary-button compact'} type="button" onClick={onConfirm}>
          {actionLabel}
        </button>
      </div>
    </Modal>
  )
}

function UserDrawer({ user, onClose }) {
  if (!user) {
    return null
  }

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

        <section className="drawer-section">
          <h3>Assigned Categories</h3>
          <div className="category-list">
            {user.assignedCategories.map((category) => (
              <span key={category}>{category}</span>
            ))}
          </div>
        </section>

        <section className="drawer-section">
          <h3>Recent Activities</h3>
          <ul className="activity-list">
            {user.activities.map((activity) => (
              <li key={activity}>{activity}</li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}

function Users({ currentUser, onLogout }) {
  const [users, setUsers] = useState(INITIAL_USERS)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('All Roles')
  const [statusFilter, setStatusFilter] = useState('All')
  const [actionUserId, setActionUserId] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [modal, setModal] = useState(null)
  const [notification, setNotification] = useState('')

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

  function openModal(type, user = null) {
    setActionUserId(null)
    setSelectedUser(user)
    setModal(type)
  }

  function closeModal() {
    setModal(null)
    setSelectedUser(null)
  }

  function createUser(values) {
    const nextUser = {
      id: Date.now(),
      fullName: values.fullName.trim(),
      email: values.email.trim(),
      role: values.role,
      status: values.status,
      createdDate: 'Jun 15, 2026',
      lastLogin: 'Never',
      assignedConversations: 0,
      assignedCategories: [],
      activities: ['User account created'],
    }
    setUsers((current) => [nextUser, ...current])
    closeModal()
    showNotification('User created successfully.')
  }

  function updateUser(values) {
    setUsers((current) =>
      current.map((user) =>
        user.id === selectedUser.id
          ? {
              ...user,
              fullName: values.fullName.trim(),
              email: values.email.trim(),
              role: values.role,
              status: values.status,
            }
          : user,
      ),
    )
    closeModal()
    showNotification('User updated successfully.')
  }

  function setUserStatus(user, status) {
    setUsers((current) => current.map((item) => (item.id === user.id ? { ...item, status } : item)))
    closeModal()
    showNotification(status === 'Active' ? 'User activated successfully.' : 'User disabled successfully.')
  }

  function resetPassword() {
    closeModal()
    showNotification('Password reset notification sent.')
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

        <section className="table-card" aria-label="Users table">
          {filteredUsers.length ? (
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
                              onClick={() => {
                                setActionUserId(null)
                                setSelectedUser(user)
                              }}
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
                              <button className="menu-disable" type="button" onClick={() => openModal('disable', user)}>
                                <Icon name="disable" />
                                Disable User
                              </button>
                            ) : (
                              <button className="menu-activate" type="button" onClick={() => setUserStatus(user, 'Active')}>
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
          <UserForm mode="create" initialValues={EMPTY_FORM} onCancel={closeModal} onSubmit={createUser} />
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
            onCancel={closeModal}
            onSubmit={updateUser}
          />
        </Modal>
      ) : null}

      {modal === 'reset' && selectedUser ? (
        <ConfirmModal
          title="Reset Password"
          message="Are you sure you want to reset this user's password?"
          actionLabel="Reset Password"
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
          onCancel={closeModal}
          onConfirm={() => setUserStatus(selectedUser, 'Inactive')}
        />
      ) : null}

      <UserDrawer user={selectedUser && !modal ? selectedUser : null} onClose={() => setSelectedUser(null)} />
    </AppLayout>
  )
}

export default Users

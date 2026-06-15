import { useMemo, useState } from 'react'

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

const SIDEBAR_ITEMS = [
  'Dashboard',
  'Conversations',
  'Templates',
  'Categories',
  'Notifications',
  'Analytics',
  'eBay Accounts',
  'Users',
  'Audit Logs',
  'Settings',
]

const NAV_ICONS = {
  Dashboard: 'home',
  Conversations: 'chat',
  Templates: 'template',
  Categories: 'list',
  Notifications: 'bell',
  Analytics: 'chart',
  'eBay Accounts': 'bag',
  Users: 'users',
  'Audit Logs': 'refresh',
  Settings: 'settings',
}

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

function Icon({ name }) {
  const paths = {
    home: <path d="M3 10.5 10 4l7 6.5V18h-5v-5H8v5H3v-7.5Z" />,
    chat: <path d="M4 5h12v8H8l-4 4V5Z" />,
    template: <path d="M4 4h12v14H4V4Zm3 4h6M7 12h6" />,
    list: <path d="M5 6h10M5 10h10M5 14h10M3 6h.01M3 10h.01M3 14h.01" />,
    bell: <path d="M6 15h8l-1-2V9a4 4 0 0 0-8 0v4l-1 2h2Zm3 2h2" />,
    chart: <path d="M4 16h12M6 13V8m4 5V5m4 8v-3" />,
    bag: <path d="M5 7h10l1 10H4L5 7Zm3 0a2 2 0 0 1 4 0" />,
    users: <path d="M7 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm6 8v-1a5 5 0 0 0-10 0v1m10-8a2.5 2.5 0 1 0 0-5m2 13v-1a4 4 0 0 0-3-3.87" />,
    refresh: <path d="M15 6a6 6 0 1 0 1 6m0-6h-4m4 0V2" />,
    settings: <path d="M10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7-3-2-.7-.4-1 1-1.9-2-2-1.9 1-1-.4L10 2H7l-.7 2-1 .4-1.9-1-2 2 1 1.9-.4 1L0 9v3l2 .7.4 1-1 1.9 2 2 1.9-1 1 .4.7 2h3l.7-2 1-.4 1.9 1 2-2-1-1.9.4-1 2-.7V9Z" />,
    plus: <path d="M10 4v12M4 10h12" />,
    dots: <path d="M5 10h.01M10 10h.01M15 10h.01" />,
    eye: <path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5Zm8 2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />,
    edit: <path d="m4 14-.5 2.5L6 16l8.5-8.5-2-2L4 14Zm9-10 2 2" />,
    key: <path d="M7 11a4 4 0 1 1 3.5 2H9l-1.5 1.5H6V16H4v-2h2l2.1-2.1A4 4 0 0 1 7 11Zm4-1h.01" />,
    disable: <path d="M4.5 4.5 15.5 15.5M17 10a7 7 0 0 1-10.8 5.9M3 10A7 7 0 0 1 13.8 4.1" />,
    activate: <path d="m4 10 4 4 8-8" />,
    moon: <path d="M14.5 13.5A6 6 0 0 1 7 6a6 6 0 1 0 7.5 7.5Z" />,
  }

  return (
    <svg className="ui-icon" viewBox="0 0 20 20" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function Shell({ children }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span>OD</span>
          <div>
            <strong>Omni-Desk</strong>
            <p>eBay Helpdesk</p>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {SIDEBAR_ITEMS.map((item) => (
            <a className={item === 'Users' ? 'active' : ''} href={item === 'Users' ? '/users' : '#'} key={item}>
              <span>
                <Icon name={NAV_ICONS[item]} />
              </span>
              {item}
            </a>
          ))}
        </nav>

        <div className="sidebar-user">
          <span>AS</span>
          <div>
            <strong>Anika Shah</strong>
            <p>Admin</p>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="top-nav">
          <label className="global-search">
            <span>Search</span>
            <input type="search" placeholder="Search conversations, users, orders" />
          </label>
          <div className="top-actions">
            <button className="icon-button" type="button" aria-label="Notifications">
              <Icon name="bell" />
              <span className="notify-dot">3</span>
            </button>
            <button className="icon-button" type="button" aria-label="Theme">
              <Icon name="moon" />
            </button>
            <button className="profile-button" type="button">
              <span>AS</span>
              Admin
            </button>
          </div>
        </header>

        {children}
      </div>
    </div>
  )
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

function Users() {
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
    <Shell>
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
    </Shell>
  )
}

export default Users

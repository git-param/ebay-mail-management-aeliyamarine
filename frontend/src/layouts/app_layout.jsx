import { useEffect, useState } from 'react'

import { normalizeRole } from '../utils/roles'
import { fetchNotifications, markNotificationsRead } from '../services/notificationApi'

const NAV_ITEMS = [
  {
    label: 'Inbox',
    path: '/inbox',
    icon: 'home',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Users',
    path: '/users',
    icon: 'users',
    roles: ['ADMIN'],
  },
  {
    label: 'eBay Accounts',
    path: '/ebay-accounts',
    icon: 'bag',
    roles: ['ADMIN'],
  },
  {
    label: 'Categories',
    path: '/categories',
    icon: 'tag',
    roles: ['ADMIN', 'OPS_MANAGER'],
  },
  {
    label: 'Analytics',
    path: '/analytics',
    icon: 'chart',
    roles: ['ADMIN', 'OPS_MANAGER'],
  },
  {
    label: 'Audit Logs',
    path: '/audit-logs',
    icon: 'audit',
    roles: ['ADMIN'],
  },
]

function getInitials(name) {
  if (!name) {
    return 'OD'
  }

  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function Icon({ name }) {
  const paths = {
    home: <path d="M3 10.5 10 4l7 6.5V18h-5v-5H8v5H3v-7.5Z" />,
    users: <path d="M7 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm6 8v-1a5 5 0 0 0-10 0v1m10-8a2.5 2.5 0 1 0 0-5m2 13v-1a4 4 0 0 0-3-3.87" />,
    bag: <path d="M5 7h10l1 10H4L5 7Zm3 0a2 2 0 0 1 4 0" />,
    tag: <path d="M4 4h6l6 6-6 6-6-6V4Zm4 3h.01" />,
    plus: <path d="M10 4v12M4 10h12" />,
    dots: <path d="M5 10h.01M10 10h.01M15 10h.01" />,
    eye: <path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5Zm8 2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />,
    edit: <path d="m4 14-.5 2.5L6 16l8.5-8.5-2-2L4 14Zm9-10 2 2" />,
    key: <path d="M7 11a4 4 0 1 1 3.5 2H9l-1.5 1.5H6V16H4v-2h2l2.1-2.1A4 4 0 0 1 7 11Zm4-1h.01" />,
    disable: <path d="M4.5 4.5 15.5 15.5M17 10a7 7 0 0 1-10.8 5.9M3 10A7 7 0 0 1 13.8 4.1" />,
    activate: <path d="m4 10 4 4 8-8" />,
    close: <path d="M5 5l10 10M15 5 5 15" />,
    bell: <path d="M6 15h8l-1-2V9a4 4 0 0 0-8 0v4l-1 2h2Zm3 2h2" />,
    message: <path d="M4 5h12v8H7l-3 3V5Zm3 3h6M7 10h4" />,
    moon: <path d="M14.5 13.5A6 6 0 0 1 7 6a6 6 0 1 0 7.5 7.5Z" />,
    chart: <path d="M4 16V5m0 11h12M7 13V9m4 4V6m4 7v-3" />,
    audit: <path d="M5 4h8l2 2v10H5V4Zm7 0v3h3M7 9h6M7 12h6" />,
  }

  return (
    <svg className="ui-icon" viewBox="0 0 20 20" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function AppLayout({ activePage, children, currentUser, onLogout }) {
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')
  const userRole = normalizeRole(currentUser?.role)
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(userRole))
  const displayName = currentUser?.full_name || currentUser?.fullName || currentUser?.email || 'User'
  const roleLabel = currentUser?.role || userRole

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    let isActive = true
    async function loadNotifications() {
      try {
        const response = await fetchNotifications()
        if (isActive) {
          setNotifications(response.items || [])
          setUnreadCount(response.unread_count || 0)
        }
      } catch {
        if (isActive) {
          setNotifications([])
          setUnreadCount(0)
        }
      }
    }
    loadNotifications()
    const interval = window.setInterval(loadNotifications, 60000)
    return () => {
      isActive = false
      window.clearInterval(interval)
    }
  }, [])

  async function toggleNotifications() {
    const nextOpen = !isNotificationsOpen
    setIsNotificationsOpen(nextOpen)
    if (nextOpen && unreadCount) {
      try {
        await markNotificationsRead()
        setUnreadCount(0)
        setNotifications((items) => items.map((item) => ({ ...item, is_read: true })))
      } catch {
        // Keep the menu usable even if marking read fails.
      }
    }
  }

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
          {visibleItems.map((item) => (
            <a className={item.label === activePage ? 'active' : ''} href={item.path} key={item.label}>
              <span>
                <Icon name={item.icon} />
              </span>
              {item.label}
            </a>
          ))}
        </nav>

        <div className="sidebar-user">
          <span>{getInitials(displayName)}</span>
          <div>
            <strong>{displayName}</strong>
            <p>{roleLabel}</p>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="top-nav">
          <div className="top-actions">
            <div className="notification-menu-wrap">
            <button
              className="icon-button"
              type="button"
              aria-label="Notifications"
              aria-expanded={isNotificationsOpen}
              onClick={toggleNotifications}
            >
              <Icon name="bell" />
              <span className="notify-dot">{unreadCount}</span>
            </button>
              {isNotificationsOpen ? (
                <div className="notification-menu">
                  <strong>Notifications</strong>
                  {notifications.length ? (
                    notifications.map((notification) => (
                      <a href={notification.resource_type === 'CONVERSATION' ? `/inbox` : '#'} key={notification.id}>
                        <span>{notification.title}</span>
                        <p>{notification.body}</p>
                      </a>
                    ))
                  ) : (
                    <p>No new notifications right now.</p>
                  )}
                </div>
              ) : null}
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Theme"
              onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
            >
              <Icon name="moon" />
            </button>
            <div className="profile-menu-wrap">
              <button
                className="profile-button"
                type="button"
                onClick={() => setIsProfileOpen((current) => !current)}
                aria-expanded={isProfileOpen}
              >
                <span>{getInitials(displayName)}</span>
                {displayName}
              </button>
              {isProfileOpen ? (
                <div className="profile-menu">
                  <p>{roleLabel}</p>
                  <button type="button" onClick={onLogout}>
                    Logout
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {children}
      </div>
    </div>
  )
}

export default AppLayout

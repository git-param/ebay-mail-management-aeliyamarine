import { useEffect, useRef, useState } from 'react'

import { normalizeRole } from '../utils/roles'
import { deleteAllNotifications, deleteNotification, fetchNotifications, markNotificationsRead } from '../services/notificationApi'
import './app_layout.css'

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
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Templates',
    path: '/templates',
    icon: 'message',
    roles: ['ADMIN', 'OPS_MANAGER'],
  },
  {
    label: 'Analytics',
    path: '/analytics',
    icon: 'chart',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Message Types', path: '/message-types', icon: 'tag', roles: ['ADMIN'],
  },
  {
    label: 'Message Reports', path: '/message-reports', icon: 'chart', roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Offer Management',
    path: '/offer-management',
    icon: 'handshake',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Sold Posting',
    path: '/sold-posting',
    icon: 'package',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Daily Task Entry',
    path: '/daily-task-entry',
    icon: 'audit',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Task Management',
    path: '/task-management',
    icon: 'settings',
    roles: ['ADMIN'],
  },
  {
    label: 'Search Across Platforms',
    path: '/search-across-platforms',
    icon: 'search',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Audit Logs',
    path: '/audit-logs',
    icon: 'audit',
    roles: ['ADMIN'],
  },
  {
    label: 'PMS',
    path: '/pms',
    icon: 'pms',
    roles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    label: 'Config',
    path: '/config',
    icon: 'settings',
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

function formatNotificationTime(value) {
  if (!value) {
    return 'Just now'
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
    copy: <path d="M7 7h8v10H7V7Zm-2 6H4V3h8v1" />,
    chevron: <path d="m5 8 5 5 5-5" />,
    menu: <path d="M3 5h14M3 10h14M3 15h14" />,
    bell: <path d="M6 15h8l-1-2V9a4 4 0 0 0-8 0v4l-1 2h2Zm3 2h2" />,
    message: <path d="M4 5h12v8H7l-3 3V5Zm3 3h6M7 10h4" />,
    paperclip: <path d="M7.5 10.5 12 6a2.1 2.1 0 0 1 3 3l-6.2 6.2a3.4 3.4 0 0 1-4.8-4.8l6.1-6.1M6.5 12.5l6.1-6.1" />,
    reply: <path d="M8 6 4 10l4 4v-3h3.5A4.5 4.5 0 0 1 16 15.5V15a7 7 0 0 0-7-7H8V6Z" />,
    moon: <path d="M14.5 13.5A6 6 0 0 1 7 6a6 6 0 1 0 7.5 7.5Z" />,
    chart: <path d="M4 16V5m0 11h12M7 13V9m4 4V6m4 7v-3" />,
    audit: <path d="M5 4h8l2 2v10H5V4Zm7 0v3h3M7 9h6M7 12h6" />,
    search: <path d="M8.5 14a5.5 5.5 0 1 1 3.9-1.6L16 16l-1.4 1.4-3.6-3.6A5.5 5.5 0 0 1 8.5 14Zm0-2a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />,
    refresh: <path d="M16 6V3m0 0h-3m3 0-2.3 2.3A6 6 0 1 0 16 11" />,
    filter: <path d="M3 4h14l-5.5 6v5L8.5 16.5V10L3 4Z" />,
    clock: <path d="M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm0 3v4l2.7 1.6" />,
    handshake: <path d="M7 8.5 9.2 6.3a2 2 0 0 1 2.8 0l.7.7H15l2 3-2.5 4.5h-2.2L10 16.2 7.7 14H5.5L3 9.5l2-3h2l.8.8L6.2 9 8 10.8l1.4-1.4M5.5 14.5 3 10m12 4.5 2-4m-5-3.5 2.8 2.8a1.4 1.4 0 0 1 0 2L12 14.5" />,
    package: <path d="m3 6.5 7-3.5 7 3.5v7L10 17l-7-3.5v-7Zm7 3.5 7-3.5M10 10 3 6.5m7 3.5V17" />,
    trash: <path d="M6 7h8m-7 0 .6 9h4.8L13 7M8 7V5h4v2M9 10v4m2-4v4" />,
    external: <path d="M8 5H5v10h10v-3M11 5h4v4m0-4-6 6" />,
    settings: <path d="M8.8 3h2.4l.4 2a5.8 5.8 0 0 1 1.2.5l1.8-1.1 1.2 2.1-1.5 1.3c.1.4.2.8.2 1.2s-.1.8-.2 1.2l1.5 1.3-1.2 2.1-1.8-1.1a5.8 5.8 0 0 1-1.2.5l-.4 2H8.8l-.4-2a5.8 5.8 0 0 1-1.2-.5l-1.8 1.1-1.2-2.1 1.5-1.3A5 5 0 0 1 5.5 9c0-.4.1-.8.2-1.2L4.2 6.5l1.2-2.1 1.8 1.1c.4-.2.8-.4 1.2-.5l.4-2Zm1.2 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />,
    pms: <path d="M7 4h1.2a2 2 0 0 1 3.6 0H13a2 2 0 0 1 2 2v11H5V6a2 2 0 0 1 2-2Zm1 0v2h4V4M8 10l1.5 1.5L12.5 8M8 14h4" />,
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const userRole = normalizeRole(currentUser?.role)
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(userRole))
  const displayName = currentUser?.full_name || currentUser?.fullName || currentUser?.email || 'User'
  const roleLabel = currentUser?.role || userRole
  const notificationMenuRef = useRef(null)
  const profileMenuRef = useRef(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') {
        setIsSidebarOpen(false)
        setIsNotificationsOpen(false)
        setIsProfileOpen(false)
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  useEffect(() => {
    function closePopovers(event) {
      if (notificationMenuRef.current && !notificationMenuRef.current.contains(event.target)) {
        setIsNotificationsOpen(false)
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setIsProfileOpen(false)
      }
    }

    document.addEventListener('mousedown', closePopovers)
    return () => document.removeEventListener('mousedown', closePopovers)
  }, [])

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
    if (nextOpen) setIsProfileOpen(false)
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

  async function removeNotification(notificationId, event) {
    event.preventDefault()
    event.stopPropagation()
    try {
      await deleteNotification(notificationId)
      setNotifications((items) => items.filter((item) => item.id !== notificationId))
      setUnreadCount((count) => {
        const removed = notifications.find((item) => item.id === notificationId)
        return removed && !removed.is_read ? Math.max(0, count - 1) : count
      })
    } catch {
      // Leave the item visible if deletion fails.
    }
  }

  async function clearNotifications() {
    try {
      await deleteAllNotifications()
      setNotifications([])
      setUnreadCount(0)
    } catch {
      // Keep notifications visible if deletion fails.
    }
  }

  return (
    <div className={`app-shell ${isSidebarOpen ? 'sidebar-is-open' : ''}`}>
      <button
        className="sidebar-backdrop"
        type="button"
        aria-label="Close navigation"
        onClick={() => setIsSidebarOpen(false)}
      />
      <aside className="sidebar" aria-label="Application navigation">
        <div className="sidebar-brand">
          <span>AM</span>
          <div>
            <strong>ACES</strong>
            <p>Aeliya Communications & Engagement System</p>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {visibleItems.map((item) => (
            <a className={item.label === activePage ? 'active' : ''} href={item.path} key={item.label} onClick={() => setIsSidebarOpen(false)}>
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
          <button
            className="icon-button mobile-menu-button"
            type="button"
            aria-label="Open navigation"
            aria-expanded={isSidebarOpen}
            onClick={() => setIsSidebarOpen((current) => !current)}
          >
            <Icon name={isSidebarOpen ? 'close' : 'menu'} />
          </button>
          <div className="top-actions">
            <div className="notification-menu-wrap" ref={notificationMenuRef}>
              <button
                className={`icon-button notification-trigger ${unreadCount ? 'has-unread' : ''}`}
                type="button"
                aria-label="Notifications"
                aria-expanded={isNotificationsOpen}
                onClick={toggleNotifications}
              >
                <Icon name="bell" />
                {unreadCount ? <span className="notify-dot">{unreadCount}</span> : null}
              </button>
              {isNotificationsOpen ? (
                <div className="notification-menu">
                  <div className="notification-menu-header">
                    <div>
                      <strong>Notifications</strong>
                      <p>{unreadCount ? `${unreadCount} unread alert${unreadCount === 1 ? '' : 's'}` : 'All caught up'}</p>
                    </div>
                    {notifications.length ? <button className="notification-clear-button" type="button" onClick={clearNotifications}>Clear all</button> : null}
                  </div>
                  {notifications.length ? (
                    notifications.map((notification) => (
                      <a
                        className={`notification-item ${notification.is_read ? '' : 'unread'}`}
                        href={notification.resource_type === 'CONVERSATION' && notification.resource_id ? `/inbox?conversation_id=${encodeURIComponent(notification.resource_id)}` : '#'}
                        key={notification.id}
                        onClick={() => setIsNotificationsOpen(false)}
                      >
                        <div className="notification-item-content">
                          <span>
                            <span className="notification-pulse" aria-hidden="true" />
                            {notification.title}
                          </span>
                          <p>{notification.body}</p>
                          <time>{formatNotificationTime(notification.created_at || notification.createdAt)}</time>
                        </div>
                        <button className="notification-delete-button" type="button" aria-label="Delete notification" onClick={(event) => removeNotification(notification.id, event)}>
                          <Icon name="close" />
                        </button>
                      </a>
                    ))
                  ) : (
                    <div className="notification-empty">
                      <Icon name="bell" />
                      <p>No new notifications right now.</p>
                    </div>
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
            <div className="profile-menu-wrap" ref={profileMenuRef}>
              <button
                className="profile-button"
                type="button"
                onClick={() => {
                  setIsProfileOpen((current) => !current)
                  setIsNotificationsOpen(false)
                }}
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
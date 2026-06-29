import { useState } from 'react'

import Categories from './pages/categories'
import Analytics from './pages/analytics'
import AuditLogs from './pages/audit_logs'
import Dashboard from './pages/dashboard'
import EbayAccounts from './pages/ebay_accounts'
import ForgotPassword from './pages/forgot_password'
import Login from './pages/login'
import LoginSuccess from './pages/login_success'
import ResetPassword from './pages/reset_password'
import Templates from './pages/templates'
import Users from './pages/users'
import MessageTypes from './pages/message_types'
import MessageReports from './pages/message_reports'
import { logoutUser } from './services/authApi'
import { clearStoredSession } from './services/http'
import { normalizeRole } from './utils/roles'
import './App.css'

const PUBLIC_ROUTES = [
  {
    path: '/',
    component: Login,
  },
  {
    path: '/login',
    component: Login,
  },
  {
    path: '/forgot-password',
    component: ForgotPassword,
  },
  {
    path: '/reset-password',
    component: ResetPassword,
  },
  {
    path: '/login-success',
    component: LoginSuccess,
  },
]

const PROTECTED_ROUTES = [
  {
    path: '/inbox',
    component: Dashboard,
    allowedRoles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    path: '/dashboard',
    component: Dashboard,
    allowedRoles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    path: '/users',
    component: Users,
    allowedRoles: ['ADMIN'],
  },
  {
    path: '/ebay-accounts',
    component: EbayAccounts,
    allowedRoles: ['ADMIN'],
  },
  {
    path: '/categories',
    component: Categories,
    allowedRoles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    path: '/templates',
    component: Templates,
    allowedRoles: ['ADMIN', 'OPS_MANAGER'],
  },
  {
    path: '/analytics',
    component: Analytics,
    allowedRoles: ['ADMIN', 'OPS_MANAGER', 'AGENT'],
  },
  {
    path: '/message-types', component: MessageTypes, allowedRoles: ['ADMIN'],
  },
  {
    path: '/message-reports', component: MessageReports, allowedRoles: ['ADMIN', 'OPS_MANAGER'],
  },
  {
    path: '/audit-logs',
    component: AuditLogs,
    allowedRoles: ['ADMIN'],
  },
]

function getStoredAuth() {
  const currentUser = localStorage.getItem('currentUser')

  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')

  if (!currentUser) {
    return {
      currentUser: null,
    }
  }

  try {
    return {
      currentUser: JSON.parse(currentUser),
    }
  } catch {
    clearStoredSession()
    return {
      currentUser: null,
    }
  }
}

function normalizePath(pathname) {
  if (!pathname || pathname === '/') {
    return '/'
  }

  return pathname.replace(/\/+$/, '').toLowerCase()
}

function NotFound() {
  return (
    <main className="auth-page">
      <section className="auth-panel auth-panel-small" aria-labelledby="not-found-title">
        <div className="auth-form-wrap">
          <p className="auth-brand">Mail Management</p>
          <p className="auth-eyebrow">Page Not Found</p>
          <h1 id="not-found-title">We could not find that page</h1>
          <p className="auth-subtitle">
            The page you requested does not exist or may have been moved.
          </p>
          <a className="primary-button auth-link-button" href="/login">
            Back to login
          </a>
        </div>
      </section>
    </main>
  )
}

function Redirect({ to }) {
  window.location.replace(to)
  return null
}

function App() {
  const [auth, setAuth] = useState(getStoredAuth)
  const currentPath = normalizePath(window.location.pathname)
  const isAuthenticated = Boolean(auth.currentUser)
  const currentRole = normalizeRole(auth.currentUser?.role)

  async function logout() {
    try {
      await logoutUser()
    } catch {
      // Local cleanup must still happen if the server session already expired.
    }
    clearStoredSession()
    setAuth({
      currentUser: null,
    })
    window.location.assign('/login')
  }

  if (isAuthenticated && ['/', '/login', '/forgot-password', '/reset-password', '/login-success'].includes(currentPath)) {
    return <Redirect to="/inbox" />
  }

  const publicRoute = PUBLIC_ROUTES.find(({ path }) => path === currentPath)
  if (publicRoute) {
    const Page = publicRoute.component
    return <Page />
  }

  const protectedRoute = PROTECTED_ROUTES.find(({ path }) => path === currentPath)
  if (protectedRoute) {
    if (!isAuthenticated) {
      return <Redirect to="/login" />
    }

    if (!['/dashboard', '/inbox'].includes(protectedRoute.path) && !protectedRoute.allowedRoles.includes(currentRole)) {
      return <Redirect to="/inbox" />
    }

    const Page = protectedRoute.component
    return <Page currentUser={auth.currentUser} onLogout={logout} />
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />
  }

  return <NotFound />
}

export default App

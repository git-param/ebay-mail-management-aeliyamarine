import ForgotPassword from './pages/forgot_password'
import Login from './pages/login'
import './App.css'

const ROUTES = [
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
]

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

function App() {
  const currentPath = normalizePath(window.location.pathname)
  const route = ROUTES.find(({ path }) => path === currentPath)
  const Page = route?.component ?? NotFound

  return <Page />
}

export default App

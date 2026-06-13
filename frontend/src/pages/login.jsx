import { LOGIN_TEXT } from '../constants/loginConstants'

function Login() {
  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-form-wrap">
          <p className="auth-brand">{LOGIN_TEXT.brand}</p>
          <p className="auth-eyebrow">{LOGIN_TEXT.eyebrow}</p>
          <h1 id="login-title">{LOGIN_TEXT.title}</h1>
          <p className="auth-subtitle">{LOGIN_TEXT.subtitle}</p>

          <form className="auth-form">
            <label className="field">
              <span>{LOGIN_TEXT.emailLabel}</span>
              <input
                type="email"
                name="email"
                placeholder={LOGIN_TEXT.emailPlaceholder}
                autoComplete="email"
                required
              />
            </label>

            <label className="field">
              <span>{LOGIN_TEXT.passwordLabel}</span>
              <input
                type="password"
                name="password"
                placeholder={LOGIN_TEXT.passwordPlaceholder}
                autoComplete="current-password"
                required
              />
            </label>

            <div className="form-row">
              <p>{LOGIN_TEXT.helper}</p>
              <a href="/forgot-password">{LOGIN_TEXT.forgotPassword}</a>
            </div>

            <button className="primary-button" type="submit">
              {LOGIN_TEXT.submit}
            </button>
          </form>
        </div>

        <aside className="auth-side" aria-label="Login overview">
          <div>
            <span className="status-dot"></span>
            <p>{LOGIN_TEXT.sideTitle}</p>
            <strong>{LOGIN_TEXT.sideDescription}</strong>
          </div>
        </aside>
      </section>
    </main>
  )
}

export default Login

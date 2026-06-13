import { FORGOT_PASSWORD_TEXT } from '../constants/loginConstants'

function ForgotPassword() {
  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="forgot-password-title">
        <div className="auth-form-wrap">
          <p className="auth-brand">{FORGOT_PASSWORD_TEXT.brand}</p>
          <p className="auth-eyebrow">{FORGOT_PASSWORD_TEXT.eyebrow}</p>
          <h1 id="forgot-password-title">{FORGOT_PASSWORD_TEXT.title}</h1>
          <p className="auth-subtitle">{FORGOT_PASSWORD_TEXT.subtitle}</p>

          <form className="auth-form">
            <label className="field">
              <span>{FORGOT_PASSWORD_TEXT.emailLabel}</span>
              <input
                type="email"
                name="email"
                placeholder={FORGOT_PASSWORD_TEXT.emailPlaceholder}
                autoComplete="email"
                required
              />
            </label>

            <button className="primary-button" type="submit">
              {FORGOT_PASSWORD_TEXT.submit}
            </button>

            <div className="form-row single">
              <p>{FORGOT_PASSWORD_TEXT.helper}</p>
              <a href="/">{FORGOT_PASSWORD_TEXT.backToLogin}</a>
            </div>
          </form>
        </div>

        <aside className="auth-side red" aria-label="Password reset overview">
          <div>
            <span className="status-dot"></span>
            <p>{FORGOT_PASSWORD_TEXT.sideTitle}</p>
            <strong>{FORGOT_PASSWORD_TEXT.sideDescription}</strong>
          </div>
        </aside>
      </section>
    </main>
  )
}

export default ForgotPassword

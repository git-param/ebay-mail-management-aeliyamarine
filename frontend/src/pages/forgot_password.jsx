import { useState } from 'react'

import { FORGOT_PASSWORD_TEXT } from '../constants/loginConstants'
import { requestPasswordReset } from '../services/authApi'

function ForgotPassword() {
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')
    setIsSubmitting(true)

    const formData = new FormData(event.currentTarget)

    try {
      const response = await requestPasswordReset({
        email: formData.get('email'),
      })
      setMessage(response.message)
    } catch (caughtError) {
      setError(caughtError.message || FORGOT_PASSWORD_TEXT.defaultError)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="forgot-password-title">
        <div className="auth-form-wrap">
          <p className="auth-brand">{FORGOT_PASSWORD_TEXT.brand}</p>
          <p className="auth-eyebrow">{FORGOT_PASSWORD_TEXT.eyebrow}</p>
          <h1 id="forgot-password-title">{FORGOT_PASSWORD_TEXT.title}</h1>
          <p className="auth-subtitle">{FORGOT_PASSWORD_TEXT.subtitle}</p>

          <form className="auth-form" onSubmit={handleSubmit}>
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

            <button className="primary-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? FORGOT_PASSWORD_TEXT.submitting : FORGOT_PASSWORD_TEXT.submit}
            </button>

            {message ? <p className="form-message success">{message}</p> : null}

            {error ? (
              <p className="form-message error" role="alert">
                {error}
              </p>
            ) : null}

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

import { useMemo, useState } from 'react'

import { RESET_PASSWORD_TEXT } from '../../constants/loginConstants'
import { resetPassword } from '../../services/authApi'

import './reset_password.css'

function ResetPassword() 
{
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') || '', [])
  const [error, setError] = useState(token ? '' : RESET_PASSWORD_TEXT.missingTokenError)
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setMessage('')

    if (!token) {
      setError(RESET_PASSWORD_TEXT.missingTokenError)
      return
    }

    const formData = new FormData(event.currentTarget)
    const newPassword = formData.get('newPassword')
    const confirmPassword = formData.get('confirmPassword')

    if (newPassword !== confirmPassword) {
      setError(RESET_PASSWORD_TEXT.passwordMismatchError)
      return
    }

    setIsSubmitting(true)
    try {
      await resetPassword({
        token,
        new_password: newPassword,
      })
      setMessage(RESET_PASSWORD_TEXT.success)
      event.currentTarget.reset()
    } catch (caughtError) {
      setError(caughtError.message || RESET_PASSWORD_TEXT.defaultError)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="reset-password-title">
        <div className="auth-form-wrap">
          <p className="auth-brand">{RESET_PASSWORD_TEXT.brand}</p>
          <p className="auth-eyebrow">{RESET_PASSWORD_TEXT.eyebrow}</p>
          <h1 id="reset-password-title">{RESET_PASSWORD_TEXT.title}</h1>
          <p className="auth-subtitle">{RESET_PASSWORD_TEXT.subtitle}</p>

          <form className="auth-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>{RESET_PASSWORD_TEXT.passwordLabel}</span>
              <input
                type="password"
                name="newPassword"
                placeholder={RESET_PASSWORD_TEXT.passwordPlaceholder}
                autoComplete="new-password"
                minLength="6"
                required
                disabled={!token || Boolean(message)}
              />
            </label>

            <label className="field">
              <span>{RESET_PASSWORD_TEXT.confirmPasswordLabel}</span>
              <input
                type="password"
                name="confirmPassword"
                placeholder={RESET_PASSWORD_TEXT.confirmPasswordPlaceholder}
                autoComplete="new-password"
                minLength="6"
                required
                disabled={!token || Boolean(message)}
              />
            </label>

            <p className="form-helper">{RESET_PASSWORD_TEXT.helper}</p>

            <button className="primary-button" type="submit" disabled={isSubmitting || !token || Boolean(message)}>
              {isSubmitting ? RESET_PASSWORD_TEXT.submitting : RESET_PASSWORD_TEXT.submit}
            </button>

            {message ? <p className="form-message success">{message}</p> : null}

            {error ? (
              <p className="form-message error" role="alert">
                {error}
              </p>
            ) : null}

            <div className="form-row single">
              <a href="/login">{RESET_PASSWORD_TEXT.backToLogin}</a>
            </div>
          </form>
        </div>

        <aside className="auth-side red" aria-label="Password reset overview">
          <div>
            <span className="status-dot"></span>
            <p>{RESET_PASSWORD_TEXT.sideTitle}</p>
            <strong>{RESET_PASSWORD_TEXT.sideDescription}</strong>
          </div>
        </aside>
      </section>
    </main>
  )
}

export default ResetPassword

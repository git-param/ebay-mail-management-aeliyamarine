import { useEffect, useState } from 'react'

import { Icon } from '../../layouts/app_layout'
import { endBreak, fetchBreakStatus, startBreak } from '../../services/breakManagementApi'
import './break_maagement.css'

const BREAK_REASONS = ['Lunch', 'Tea Break']

function BreakStartModal({ isSubmitting, error, onSubmit, onClose }) {
  const [reason, setReason] = useState(BREAK_REASONS[0])
  const [customReason, setCustomReason] = useState('')
  const selectedReason = reason === 'Other' ? customReason.trim() : reason

  function submit(event) {
    event.preventDefault()
    if (!selectedReason) return
    onSubmit(selectedReason)
  }

  return (
    <div className="breakModule-modal-backdrop" onMouseDown={onClose}>
      <form className="breakModule-start-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div className="breakModule-modal-header">
          <div>
            <span>Break Management</span>
            <h2>Start Break</h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>

        <label>
          Reason for Break
          <select value={reason} onChange={(event) => setReason(event.target.value)} autoFocus>
            {BREAK_REASONS.map((item) => <option key={item} value={item}>{item}</option>)}
            <option value="Other">Other</option>
          </select>
        </label>

        {reason === 'Other' ? (
          <label>
            Custom Reason
            <input value={customReason} onChange={(event) => setCustomReason(event.target.value)} maxLength={120} />
          </label>
        ) : null}

        {error ? <p className="breakModule-form-error" role="alert">{error}</p> : null}

        <div className="breakModule-modal-actions">
          <button type="button" className="breakModule-secondary" onClick={onClose} disabled={isSubmitting}>Cancel</button>
          <button type="submit" className="breakModule-primary" disabled={!selectedReason || isSubmitting}>
            {isSubmitting ? 'Starting...' : 'Submit'}
          </button>
        </div>
      </form>
    </div>
  )
}

function BreakActionButton({ className = '', onStatusChange }) {
  const [status, setStatus] = useState({ is_on_break: false, active_break: null })
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadStatus() {
    try {
      const response = await fetchBreakStatus()
      setStatus(response)
      onStatusChange?.(response)
    } catch {
      setStatus({ is_on_break: false, active_break: null })
    }
  }

  useEffect(() => {
    loadStatus()
    const interval = window.setInterval(loadStatus, 60000)
    return () => window.clearInterval(interval)
  }, [])

  async function submitStart(reason) {
    setIsSubmitting(true)
    setError('')
    try {
      await startBreak(reason)
      setIsModalOpen(false)
      await loadStatus()
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to start break.')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function submitEnd() {
    const confirmed = window.confirm('End your current break now?')
    if (!confirmed) return

    setIsSubmitting(true)
    setError('')
    try {
      await endBreak()
      await loadStatus()
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to end break.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const onBreak = Boolean(status.is_on_break)

  return (
    <>
      <button
        className={`secondary-button compact-action breakModule-action-button ${onBreak ? 'is-on-break' : 'is-active'} ${className}`}
        type="button"
        onClick={onBreak ? submitEnd : () => setIsModalOpen(true)}
        disabled={isSubmitting}
        title={onBreak ? `On break: ${status.active_break?.reason || 'Break'}` : 'Start a break'}
      >
        <Icon name="clock" />
        <span>{onBreak ? 'End Break' : 'Start Break'}</span>
        <span className="breakModule-status-dot" aria-hidden="true" />
      </button>
      {isModalOpen ? (
        <BreakStartModal
          isSubmitting={isSubmitting}
          error={error}
          onSubmit={submitStart}
          onClose={() => {
            if (!isSubmitting) {
              setIsModalOpen(false)
              setError('')
            }
          }}
        />
      ) : null}
    </>
  )
}

export default BreakActionButton

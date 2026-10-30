import { useEffect, useRef, useState } from 'react'

import { Icon } from '../../layouts/app_layout'
import { endBreak, fetchBreakStatus, startBreak } from '../../services/breakManagementApi'
import './break_maagement.css'

const BREAK_REASONS = ['Lunch', 'Tea Break']
const REASON_EMOJI = { Lunch: '🍱', 'Tea Break': '🍵', Other: '✨' }

function BreakStartModal({ isSubmitting, error, onSubmit, onClose, playful }) {
  const [reason, setReason] = useState(BREAK_REASONS[0])
  const [customReason, setCustomReason] = useState('')
  const selectedReason = reason === 'Other' ? customReason.trim() : reason

  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function submit(event) {
    event.preventDefault()
    if (!selectedReason) return
    onSubmit(selectedReason)
  }

  const optionLabel = (item) => (playful ? `${REASON_EMOJI[item]} ${item}` : item)

  return (
    <div className="breakModule-modal-backdrop" onMouseDown={onClose}>
      <form
        className={`breakModule-start-modal${playful ? ' is-playful' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Start break"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="breakModule-modal-header">
          <div>
            <span>{playful ? 'Tactical snack deployment' : 'Break Management'}</span>
            <h2>
              {playful ? <span className="breakModule-modal-emoji" aria-hidden="true">☕</span> : null}
              {playful ? 'Time to recharge?' : 'Start Break'}
            </h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>

        <label>
          Reason for Break
          <select value={reason} onChange={(event) => setReason(event.target.value)} autoFocus>
            {BREAK_REASONS.map((item) => <option key={item} value={item}>{optionLabel(item)}</option>)}
            <option value="Other">{optionLabel('Other')}</option>
          </select>
        </label>

        {reason === 'Other' ? (
          <label>
            Custom Reason
            <input
              value={customReason}
              onChange={(event) => setCustomReason(event.target.value)}
              maxLength={120}
              placeholder={playful ? 'e.g. Staring at a wall (productively)' : ''}
            />
          </label>
        ) : null}

        {playful ? (
          <p className="breakModule-autoreply">
            <b>📧 Auto-reply preview:</b> “I am out for {selectedReason || '…'}. I will respond with delayed enthusiasm.”
          </p>
        ) : null}

        {error ? <p className="breakModule-form-error" role="alert">{error}</p> : null}

        <div className="breakModule-modal-actions">
          <button type="button" className="breakModule-secondary" onClick={onClose} disabled={isSubmitting}>
            {playful ? 'Never mind' : 'Cancel'}
          </button>
          <button type="submit" className="breakModule-primary" disabled={!selectedReason || isSubmitting}>
            {isSubmitting ? (playful ? 'Clocking out...' : 'Starting...') : (playful ? 'Start Break' : 'Submit')}
          </button>
        </div>
      </form>
    </div>
  )
}

/* `playful` is only passed for agent users; managers always get the plain version. */
function BreakActionButton({ className = '', onStatusChange, playful = false }) {
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

  const instanceId = useRef(Math.random())

  function notifySync() {
    window.dispatchEvent(new CustomEvent('break-status-changed', { detail: instanceId.current }))
  }

  useEffect(() => {
    loadStatus()
    const interval = window.setInterval(loadStatus, 60000)
    // keep every Start/End Break button on the page in sync
    const onSync = (event) => { if (event.detail !== instanceId.current) loadStatus() }
    window.addEventListener('break-status-changed', onSync)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('break-status-changed', onSync)
    }
  }, [])

  async function submitStart(reason) {
    setIsSubmitting(true)
    setError('')
    try {
      await startBreak(reason)
      setIsModalOpen(false)
      await loadStatus()
      notifySync()
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to start break.')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function submitEnd() {
    const confirmed = window.confirm(playful ? 'Back already? End your current break now?' : 'End your current break now?')
    if (!confirmed) return

    setIsSubmitting(true)
    setError('')
    try {
      await endBreak()
      await loadStatus()
      notifySync()
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
        className={`secondary-button compact-action breakModule-action-button ${onBreak ? 'is-on-break' : 'is-active'}${playful ? ' is-playful' : ''} ${className}`}
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
          playful={playful}
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
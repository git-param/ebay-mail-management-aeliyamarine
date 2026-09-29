import { useEffect, useState } from 'react'
import { deleteAuditLogs, previewAuditDeletion } from '../../services/auditApi'

export default function AuditLogMaintenance() {
  const [dates, setDates] = useState({ date_from: '', date_to: '' })
  const [confirmation, setConfirmation] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)
  const validDates = dates.date_from && dates.date_to && dates.date_from <= dates.date_to
  const matchingPreview = preview && preview.date_from === dates.date_from && preview.date_to === dates.date_to

  useEffect(() => {
    if (!validDates) return
    let active = true
    const timer = setTimeout(() => {
      previewAuditDeletion(dates).then(result => {
        if (active) { setPreview({ ...dates, count: result.count }); setError('') }
      }).catch(err => { if (active) { setPreview(null); setError(err.message) } })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [dates, validDates, revision])

  async function removeLogs(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await deleteAuditLogs({ ...dates, confirmation })
      setMessage(`Deleted ${result.deleted_count.toLocaleString()} audit logs. A record of this deletion has been kept.`)
      setConfirmation('')
      setPreview(null)
      setRevision(value => value + 1)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  function changeDate(key, value) {
    setDates(current => ({ ...current, [key]: value }))
    setConfirmation('')
    setError('')
    setMessage('')
  }

  return <section className="table-card config-section config-danger-section">
    <div className="config-section-header"><div><h2>Delete Audit Logs</h2><p>Remove audit events within a selected date range. Both dates are included, using India time (UTC+05:30).</p></div></div>
    <form onSubmit={removeLogs}>
      <div className="config-grid">
        <label className="field config-field"><span>From date</span><input type="date" required disabled={busy} max={dates.date_to || undefined} value={dates.date_from} onChange={event => changeDate('date_from', event.target.value)} /></label>
        <label className="field config-field"><span>To date</span><input type="date" required disabled={busy} min={dates.date_from || undefined} value={dates.date_to} onChange={event => changeDate('date_to', event.target.value)} /></label>
      </div>
      <p className="confirm-message" role="status">{!validDates ? 'Choose a valid From and To date to preview the number of logs.' : matchingPreview ? `${preview.count.toLocaleString()} audit logs match this period. Deletion is permanent.` : 'Counting matching logs...'}</p>
      <label className="field config-field"><span>Type DELETE AUDIT LOGS to confirm</span><input autoComplete="off" disabled={busy} value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      {message ? <p className="form-message success" role="status">{message}</p> : null}
      <div className="modal-actions"><button className="danger-button" type="submit" disabled={busy || !validDates || !matchingPreview || !preview.count || confirmation !== 'DELETE AUDIT LOGS'}>{busy ? 'Deleting...' : 'Delete Audit Logs'}</button></div>
    </form>
  </section>
}

import { useEffect, useState } from 'react'
import { fetchBestOfferConfig, updateBestOfferConfig, syncBestOffers, fetchBestOfferJob } from '../../services/ebayBestOfferApi'
import { bestOfferDate } from './bestOfferFormat'
import './best_offers.css'

export default function BestOfferConfig() {
  const [config, setConfig] = useState(null)
  const [hours, setHours] = useState(0)
  const [minutes, setMinutes] = useState(5)
  const [selected, setSelected] = useState([])
  const [manual, setManual] = useState([])
  const [allConfigured, setAllConfigured] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [batchId, setBatchId] = useState(null)
  const [job, setJob] = useState(null)
  useEffect(() => {
    let active = true
    fetchBestOfferConfig().then(result => { if (!active) return; setConfig(result); setHours(Math.floor(result.interval_minutes/60)); setMinutes(result.interval_minutes%60); setSelected(result.account_ids); if (result.latest_job) { setBatchId(result.latest_job.id) } }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    let active = true
    const timer = setInterval(async () => {
      try {
        const result = await fetchBestOfferConfig()
        if (!active) return
        setConfig(result)
        if (result.latest_job) setBatchId(result.latest_job.id)
      } catch (err) { if (active) setError(err.message) }
    }, 5000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  useEffect(() => {
    if (!batchId) return
    let active = true
    let timer
    async function poll() {
      try { const result = await fetchBestOfferJob(batchId); if (!active) return; setJob(result); if (['PENDING','RUNNING'].includes(result.status)) timer = setTimeout(poll, 2000) }
      catch (err) { if (active) setError(err.message) }
    }
    poll()
    return () => { active = false; clearTimeout(timer) }
  }, [batchId])
  async function save(payload, message) {
    setBusy(true); setError('')
    try { setConfig(await updateBestOfferConfig(payload)); setNotice(message) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  async function sync() {
    setBusy(true); setError('')
    try { const result = await syncBestOffers(allConfigured ? null : manual); setNotice(result.status.replaceAll('_',' ')); if (result.batch_id) { setBatchId(result.batch_id); setJob({ status: 'PENDING', jobs: result.jobs }) } }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const toggle = (ids, id) => ids.includes(id) ? ids.filter(value => value !== id) : [...ids,id]
  if (!config) return <section className="best-offers-page">{error ? <p role="alert">{error}</p> : 'Loading configuration…'}</section>
  const syncing = ['PENDING', 'RUNNING'].includes(job?.status)
  const jobs = job?.jobs || []
  const completed = jobs.filter(item => item.status === 'SUCCESS').length
  const imported = jobs.reduce((total, item) => total + (item.records_processed || 0), 0)
  return <section className="best-offers-page best-offer-config">
    <header className="bo-config-hero">
      <div><span className="bo-eyebrow">OFFER MANAGEMENT</span><h1>Keep your offers in sync</h1><p>Manage your schedule, connected accounts and latest synchronization.</p></div>
      <span className={`bo-status-pill ${config.enabled ? 'enabled' : 'paused'}`}><i />{config.enabled ? 'Auto sync enabled' : 'Auto sync paused'}</span>
    </header>
    {error ? <p role="alert" className="form-message error">{error}</p> : null}
    {notice ? <p role="status" className="form-message">{notice}</p> : null}
    <div className="bo-overview">
      <div><span>Selected accounts</span><strong>{config.account_ids.length}<small> / {config.accounts.length}</small></strong></div>
      <div><span>Sync interval</span><strong>{config.interval_minutes}<small> minutes</small></strong></div>
      <div><span>Last synchronization</span><strong className="bo-overview-date">{bestOfferDate(job?.started_at || config.latest_job?.started_at)}</strong></div>
      <div><span>Next scheduled run</span><strong className="bo-overview-date">{config.enabled ? bestOfferDate(config.next_run_at) : 'Paused'}</strong></div>
    </div>
    <div className="bo-settings-grid">
      <section className="best-offer-config-card bo-schedule"><div className="bo-section-title"><span className="bo-section-icon">01</span><div><h2>Automatic synchronization</h2><p>Set how often ACES checks for fresh offers.</p></div></div>
        <div className="best-offer-form-grid"><label className="field"><span>Hours</span><input type="number" min="0" max="168" step="1" value={hours} onChange={e => setHours(e.target.value)} /></label><label className="field"><span>Minutes</span><input type="number" min="0" max="59" step="1" value={minutes} onChange={e => setMinutes(e.target.value)} /></label><button className="secondary-button" disabled={busy} onClick={() => save({ hours: Number(hours), minutes: Number(minutes) }, 'Interval saved')}>Save interval</button></div>
        <p className="bo-hint">Your schedule is saved across backend restarts.</p>
        <div className="bo-schedule-footer"><span>{config.enabled ? 'Automatic checks are enabled' : 'Manual sync remains available while paused'}</span><button className={config.enabled ? 'secondary-button' : 'primary-button'} disabled={busy} onClick={() => save({ enabled: !config.enabled }, config.enabled ? 'Auto sync paused; the current request will finish safely' : 'Auto sync started')}>{config.enabled ? 'Pause auto sync' : 'Start auto sync'}</button></div>
      </section>
      <section className="best-offer-config-card bo-accounts"><div className="bo-section-title"><span className="bo-section-icon">02</span><div><h2>Accounts to synchronize</h2><p>Select the accounts included in automatic checks.</p></div></div>
        <div className="best-offer-account-list bo-account-grid">{config.accounts.map(account => <label className={selected.includes(account.id) ? 'selected' : ''} key={account.id}><input type="checkbox" checked={selected.includes(account.id)} onChange={() => setSelected(ids => toggle(ids, account.id))} /><span className="bo-account-avatar">{account.name.slice(0,1)}</span><span><strong>{account.name}</strong><small>{account.username}</small></span></label>)}</div>
        {!config.accounts.length ? <p>No active connected accounts available.</p> : null}
        <div className="bo-account-footer"><div><button className="bo-text-button" onClick={() => setSelected(config.accounts.map(a => a.id))}>Select all</button><button className="bo-text-button" onClick={() => setSelected([])}>Clear</button></div><button className="primary-button" disabled={busy} onClick={() => save({ account_ids: selected }, 'Accounts saved')}>Save accounts</button></div>
      </section>
    </div>
    <section className="best-offer-config-card bo-manual"><div className="bo-manual-toolbar"><div className="bo-section-title"><span className="bo-section-icon">03</span><div><h2>Sync on demand</h2><p>Fetch the latest seller Best Offers whenever you need them.</p></div></div><div className="bo-manual-controls"><select aria-label="Manual synchronization accounts" value={allConfigured ? 'configured' : 'specific'} onChange={e => setAllConfigured(e.target.value === 'configured')}><option value="configured">All configured accounts</option><option value="specific">Choose accounts</option></select><button className="primary-button" disabled={busy || syncing || (!allConfigured && !manual.length) || (allConfigured && !config.account_ids.length)} onClick={sync}>{busy ? 'Requesting...' : syncing ? 'Synchronizing...' : 'Sync now'}</button></div></div>
      {!allConfigured ? <div className="best-offer-account-list bo-manual-accounts">{config.accounts.map(account => <label key={account.id}><input type="checkbox" checked={manual.includes(account.id)} onChange={() => setManual(ids => toggle(ids, account.id))} />{account.name}</label>)}</div> : null}
      {jobs.length ? <>
        <div className="bo-results-heading"><h3>Latest run <span>{syncing ? 'In progress' : `${completed} of ${jobs.length} accounts completed`}</span></h3><strong>{imported} <span>offers synchronized</span></strong></div>
        <div className="bo-results-grid">{jobs.map(accountJob => {
          const discovery = accountJob.result?.discovery
          const failed = accountJob.status === 'FAILED'
          const pending = ['PENDING', 'RUNNING'].includes(accountJob.status)
          return <article className={`best-offer-job bo-result-card ${failed ? 'failed' : ''}`} key={accountJob.id}>
            <div className="bo-result-top"><span className="bo-account-avatar">{(accountJob.result?.account_name || 'A').slice(0,1)}</span><strong>{accountJob.result?.account_name || accountJob.account_id}</strong><span className={`bo-result-status ${failed ? 'failed' : pending ? 'pending' : 'complete'}`}>{failed ? 'Needs attention' : pending ? 'Syncing' : 'Completed'}</span></div>
            <div className="bo-result-count"><strong>{accountJob.records_processed || 0}</strong><span>offers synchronized</span></div>
            <p className="bo-result-message">{pending ? 'Checking the latest offers...' : discovery?.returned === 0 ? 'Trading API returned no offer records.' : failed ? 'Some records could not be synchronized.' : 'Latest offer data saved in ACES.'}</p>
            {discovery ? <details className="bo-result-details"><summary>Response details</summary><dl><div><dt>Returned by eBay</dt><dd>{discovery.returned}</dd></div><div><dt>Verified seller records</dt><dd>{discovery.seller}</dd></div><div><dt>Buyer records skipped</dt><dd>{discovery.buyer_skipped}</dd></div><div><dt>Unknown roles skipped</dt><dd>{discovery.unknown_role_skipped}</dd></div></dl></details> : null}
            {accountJob.error ? <p role="alert" className="bo-result-error">{accountJob.error}</p> : null}
          </article>
        })}</div>
      </> : <div className="bo-run-empty"><strong>Ready when you are</strong><p>Run a synchronization to see results for each selected account.</p></div>}
    </section>
  </section>
}

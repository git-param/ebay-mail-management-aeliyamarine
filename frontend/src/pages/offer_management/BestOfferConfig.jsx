import { useEffect, useState } from 'react'
import { fetchBestOfferConfig, updateBestOfferConfig, syncBestOffers, fetchBestOfferJob, cancelBestOfferJob, authorizeOfferActivity, setupOfferActivity } from '../../services/ebayBestOfferApi'
import { bestOfferDate } from './bestOfferFormat'
import './best_offers.css'

export default function BestOfferConfig() {
  const [config, setConfig] = useState(null)
  const [hours, setHours] = useState(0)
  const [minutes, setMinutes] = useState(5)
  const [selected, setSelected] = useState([])
  const [manual, setManual] = useState([])
  const [allConfigured, setAllConfigured] = useState(true)
  const [includeHistory, setIncludeHistory] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [batchId, setBatchId] = useState(null)
  const [job, setJob] = useState(null)
  const syncing = ['PENDING', 'RUNNING'].includes(job?.status)
  useEffect(() => {
    let active = true
    fetchBestOfferConfig().then(result => { if (!active) return; setConfig(result); setHours(Math.floor(result.interval_minutes/60)); setMinutes(result.interval_minutes%60); setSelected(result.account_ids); if (result.latest_job) { setBatchId(result.latest_job.id) } }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    if (!config?.enabled || syncing) return
    let active = true
    let timer
    async function refresh() {
      try {
        const result = await fetchBestOfferConfig()
        if (!active) return
        setConfig(result)
        if (result.latest_job) setBatchId(result.latest_job.id)
      } catch (err) { if (active) setError(err.message) }
      if (active) timer = setTimeout(refresh, 60000)
    }
    timer = setTimeout(refresh, 60000)
    return () => { active = false; clearTimeout(timer) }
  }, [config?.enabled, syncing])
  useEffect(() => {
    if (!batchId) return
    let active = true
    let timer
    async function poll() {
      try {
        const result = await fetchBestOfferJob(batchId)
        if (!active) return
        setJob(result)
        if (['PENDING','RUNNING'].includes(result.status)) timer = setTimeout(poll, document.hidden ? 30000 : 10000)
        else {
          const refreshed = await fetchBestOfferConfig()
          if (active) setConfig(refreshed)
        }
      }
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
    try { const result = await syncBestOffers(allConfigured ? null : manual, includeHistory); setNotice(result.status.replaceAll('_',' ')); if (result.batch_id) { setBatchId(result.batch_id); setJob({ status: 'PENDING', jobs: result.jobs }) } }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  async function connectOfferActivity(id) {
    setBusy(true); setError('')
    try { const result = await authorizeOfferActivity(id); window.location.assign(result.authorization_url) }
    catch (err) { setError(err.message); setBusy(false) }
  }
  async function enableOfferActivity(id) {
    setBusy(true); setError('')
    try { await setupOfferActivity(id); setNotice('Offer activity connected. New offer events will be fetched on the next sync.'); setConfig(await fetchBestOfferConfig()) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  async function stopSync() {
    setBusy(true); setError('')
    try {
      const result = await cancelBestOfferJob(batchId)
      setJob(current => ({ ...current, result: result.result }))
      setNotice('Stopping synchronization after the current request finishes.')
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const toggle = (ids, id) => ids.includes(id) ? ids.filter(value => value !== id) : [...ids,id]
  if (!config) return <section className="best-offers-page">{error ? <p role="alert">{error}</p> : 'Loading configuration…'}</section>
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
    <section className="best-offer-config-card">
      <h2>Discover new offers automatically</h2>
      <p>Connect eBay offer activity for each account so sync can discover new offers and counteroffers without item IDs or eBay messages. This requires fresh eBay consent and a publicly reachable backend.</p>
      {(config.offer_activity_accounts || config.accounts).map(account => <div className="bo-schedule-footer" key={account.id}>
        <strong>{account.name}<small> ? {account.username}</small></strong>
        <span>{account.offer_activity_enabled ? 'Offer activity connected' : 'Not connected'}</span>
        <button className="secondary-button" disabled={busy || syncing} onClick={() => connectOfferActivity(account.id)}>Authorize offer access</button>
        <button className="primary-button" disabled={busy || syncing || account.offer_activity_enabled || (account.connection_status && account.connection_status !== 'CONNECTED')} onClick={() => enableOfferActivity(account.id)}>Enable offer activity</button>
      </div>)}
      <p className="bo-hint">Authorize first, then return here and enable offer activity. Keep automatic sync enabled to fetch queued offer changes.</p>
    </section>
    <section className="best-offer-config-card bo-manual"><div className="bo-manual-toolbar"><div className="bo-section-title"><span className="bo-section-icon">03</span><div><h2>Sync on demand</h2><p>Replace each account's current offers with the latest eBay result.</p></div></div><div className="bo-manual-controls"><select aria-label="Manual synchronization accounts" value={allConfigured ? 'configured' : 'specific'} onChange={e => setAllConfigured(e.target.value === 'configured')}><option value="configured">All configured accounts</option><option value="specific">Choose accounts</option></select><button className="primary-button" disabled={busy || syncing || (!allConfigured && !manual.length) || (allConfigured && !config.account_ids.length)} onClick={sync}>{busy ? 'Requesting...' : syncing ? 'Synchronizing...' : 'Sync now'}</button></div></div>
      {syncing ? <button className="secondary-button" disabled={busy || job?.result?.cancel_requested} onClick={stopSync}>{job?.result?.cancel_requested ? 'Stopping…' : 'Stop current sync'}</button> : null}
      <label className="bo-history-toggle"><input type="checkbox" checked={includeHistory} onChange={event => setIncludeHistory(event.target.checked)} disabled={busy || syncing} /> Refresh recent saved history <small>Up to 25 due listings from the last 30 days per account. Accepted and expired offers are saved automatically.</small></label>
      {!allConfigured ? <div className="best-offer-account-list bo-manual-accounts">{config.accounts.map(account => <label key={account.id}><input type="checkbox" checked={manual.includes(account.id)} onChange={() => setManual(ids => toggle(ids, account.id))} />{account.name}</label>)}</div> : null}
      {jobs.length ? <>
        <div className="bo-results-heading"><h3>Latest run <span>{syncing ? 'In progress' : `${completed} of ${jobs.length} accounts completed`}</span></h3><strong>{imported} <span>new or changed offers</span></strong></div>
        <div className="bo-results-grid">{jobs.map(accountJob => {
          const discovery = accountJob.result?.discovery
          const statistics = accountJob.result?.statistics
          const failed = accountJob.status === 'FAILED'
          const stopped = accountJob.result?.outcome === 'STOPPED'
          const pending = ['PENDING', 'RUNNING'].includes(accountJob.status)
          return <article className={`best-offer-job bo-result-card ${failed ? 'failed' : ''}`} key={accountJob.id}>
            <div className="bo-result-top"><span className="bo-account-avatar">{(accountJob.result?.account_name || 'A').slice(0,1)}</span><strong>{accountJob.result?.account_name || accountJob.account_id}</strong><span className={`bo-result-status ${failed ? 'failed' : pending ? 'pending' : 'complete'}`}>{stopped ? 'Stopped' : failed ? (discovery ? 'Partly completed' : 'Could not complete') : pending ? 'Syncing' : accountJob.result?.warnings?.length ? 'Completed with notes' : 'Completed'}</span></div>
            <div className="bo-result-count"><strong>{accountJob.records_processed || 0}</strong><span>new or changed offers</span></div>
            <p className="bo-result-message">{pending ? 'Checking current offers and decisions...' : stopped ? 'Synchronization stopped. Saved offers are preserved.' : failed ? (discovery ? 'Some offers were checked; some records could not be refreshed.' : 'The account check could not complete. See the details below.') : discovery?.returned === 0 && !statistics?.listings_reconciled ? 'eBay returned no active Best Offers for this account. This check does not include every offer type shown on eBay.' : statistics ? `${statistics.new_offers} new offers and ${statistics.updated_offers} updates saved; ${statistics.listings_reconciled} listings refreshed.` : accountJob.result?.changes?.unchanged ? `${accountJob.result.changes.unchanged} offers checked with no changes.` : discovery?.returned === 0 ? 'No active Trading offers returned. Saved history is unchanged.' : 'Latest changes saved in ACES.'}</p>
            {statistics ? <dl className="bo-sync-statistics">{[['Active discovered', statistics.active_discovered], ['Listings reconciled', statistics.listings_reconciled], ['New offers', statistics.new_offers], ['Status changes', statistics.status_changes], ['Other updates', Math.max(0, statistics.updated_offers - statistics.status_changes)], ['Unchanged observations', statistics.unchanged], ['API calls', statistics.api_calls ?? '—']].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
            {discovery ? <details className="bo-result-details"><summary>Response details</summary><dl><div><dt>Active returned by eBay</dt><dd>{discovery.returned}</dd></div><div><dt>Verified seller records</dt><dd>{discovery.seller}</dd></div><div><dt>Buyer records</dt><dd>{discovery.buyer ?? 0}</dd></div><div><dt>Unknown roles skipped</dt><dd>{discovery.unknown_role_skipped + (accountJob.result?.reconciliation?.unknown_role_skipped || 0)}</dd></div></dl></details> : null}
            {accountJob.result?.warnings?.length ? <details className="bo-result-details"><summary>{accountJob.result.warnings.length} history notes</summary>{accountJob.result.warnings.map((warning, index) => <p className="bo-result-message" key={index}>Item {warning.listing_id}: {warning.message}</p>)}</details> : null}
            {accountJob.error && !stopped ? <p role="alert" className="bo-result-error">{accountJob.result?.errors?.length ? accountJob.result.errors.map(error => `Item ${error.listing_id || error.offer_id || ''}: ${error.message || 'This older record could not be refreshed.'}`).join(' ') : accountJob.error.startsWith('[{') ? 'An older stored listing could not be refreshed. Run the latest-changes sync to check active offers.' : accountJob.error}</p> : null}
          </article>
        })}</div>
      </> : <div className="bo-run-empty"><strong>Ready when you are</strong><p>Run a synchronization to see results for each selected account.</p></div>}
    </section>
  </section>
}

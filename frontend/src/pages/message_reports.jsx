import { useEffect, useState } from 'react'

import AppLayout, { Icon } from '../layouts/app_layout'
import { exportMessageReport, fetchMessageReport, fetchMessageTypeTree } from '../services/messageTypeApi'
import { fetchUsers } from '../services/userApi'
import { fetchEbayAccounts } from '../services/ebayAccountApi'
import { normalizeRole } from '../utils/roles'

export default function MessageReports({ currentUser, onLogout }) {
  const isAgent = normalizeRole(currentUser?.role) === 'AGENT'
  const [copied, setCopied] = useState(false)
  const [filters, setFilters] = useState({
    date_from: '',
    date_to: '',
    seller_account_id: '',
    user_id: '',
    category_id: '',
    subcategory_id: '',
    search: '',
  })
  const [data, setData] = useState(null)
  const [types, setTypes] = useState([])
  const [users, setUsers] = useState([])
  const [accounts, setAccounts] = useState([])
  const [error, setError] = useState('')
  const category = types.find((item) => item.id === filters.category_id)

  async function load(next = filters) {
    try {
      setData(await fetchMessageReport(next))
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      load()
      Promise.allSettled([fetchMessageTypeTree(), isAgent ? Promise.resolve([]) : fetchUsers(), fetchEbayAccounts()])
        .then(([typeResult, userResult, accountResult]) => {
          if (typeResult.status === 'fulfilled') setTypes(typeResult.value || [])
          if (userResult.status === 'fulfilled') setUsers(userResult.value.items || userResult.value || [])
          if (accountResult.status === 'fulfilled') setAccounts(accountResult.value.items || accountResult.value || [])
        })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  function update(key, value) {
    setFilters((current) => ({
      ...current,
      [key]: value,
      ...(key === 'category_id' ? { subcategory_id: '' } : {}),
    }))
  }

  async function download() {
    try {
      const blob = await exportMessageReport(filters)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `message_report_${new Date().toISOString().slice(0, 10).replaceAll('-', '_')}.xlsx`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  function reportPeriod() {
    const format = (value) => value ? value.split('-').reverse().join('-') : ''
    if (filters.date_from && filters.date_to) {
      return filters.date_from === filters.date_to
        ? format(filters.date_from)
        : `${format(filters.date_from)} - ${format(filters.date_to)}`
    }
    if (filters.date_from || filters.date_to) return format(filters.date_from || filters.date_to)
    return 'All Time'
  }

  async function copyStats() {
    const reports = data?.employee_category_reports || []
    const text = reports.map((report) => [
      `Work Report: ${reportPeriod()}`,
      '',
      ...(!isAgent && !filters.user_id ? [`Employee: ${report.employee}`, ''] : []),
      ...report.categories.map((item) => `${item.label} - ${item.value}`),
    ].join('\n')).join('\n\n\n')
    if (!text) {
      setError('No report statistics are available to copy.')
      return
    }
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setError('')
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('Unable to copy report statistics to the clipboard.')
    }
  }

  return (
    <AppLayout activePage="Message Reports" currentUser={currentUser} onLogout={onLogout}>
      <main className="management-page">
        <div className="page-header">
          <div>
            <h1>Messaging Analytics</h1>
            <p>Internal reply classifications and productivity.</p>
          </div>
          <div className="page-header-actions">
            <button className="secondary-button compact-action" type="button" onClick={copyStats}>{copied ? 'Copied!' : 'Copy Stats'}</button>
            <button className="secondary-button compact-action" type="button" onClick={download}>Export Excel</button>
          </div>
        </div>

        <form className="analytics-filter-bar" onSubmit={(event) => { event.preventDefault(); load() }}>
          {[['date_from', 'From', 'date'], ['date_to', 'To', 'date'], ['search', 'Search', 'search']].map(([key, label, type]) => (
            <label className="field" key={key}>
              <span>{label}</span>
              <input type={type} value={filters[key]} onChange={(event) => update(key, event.target.value)} />
            </label>
          ))}
          <label className="field">
            <span>Seller</span>
            <select value={filters.seller_account_id} onChange={(event) => update('seller_account_id', event.target.value)}>
              <option value="">All</option>
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.store_name || account.ebay_username}</option>)}
            </select>
          </label>
          {!isAgent ? (
            <label className="field">
              <span>Employee</span>
              <select value={filters.user_id} onChange={(event) => update('user_id', event.target.value)}>
                <option value="">All</option>
                {users.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email}</option>)}
              </select>
            </label>
          ) : null}
          <label className="field">
            <span>Category</span>
            <select value={filters.category_id} onChange={(event) => update('category_id', event.target.value)}>
              <option value="">All</option>
              {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
            </select>
          </label>
          {category?.children?.length ? (
            <label className="field">
              <span>Sub Category</span>
              <select value={filters.subcategory_id} onChange={(event) => update('subcategory_id', event.target.value)}>
                <option value="">All</option>
                {category.children.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}
              </select>
            </label>
          ) : null}
          <button className="primary-button compact" type="submit">Apply</button>
        </form>

        {error ? <p className="form-message error">{error}</p> : null}
        <section className="stats-grid analytics-stats-grid">
          {(data?.summary || []).slice(0, 9).map((item) => (
            <article className="stat-card" key={item.label}><div><p>{item.label}</p><strong>{item.value}</strong></div></article>
          ))}
        </section>
        <section className="analytics-panel">
          <div className="report-table-wrap">
            <table>
              <thead>
                <tr>
                  {['Date', 'Time', 'Seller', 'Conversation', 'Buyer', 'Agent', 'Category', 'Sub Category', 'Preview', 'Message ID', 'Action'].map((head) => <th key={head}>{head}</th>)}
                </tr>
              </thead>
              <tbody>
                {(data?.items || []).map((item) => (
                  <tr key={item.id}>
                    <td>{new Date(item.created_at).toLocaleDateString()}</td>
                    <td>{new Date(item.created_at).toLocaleTimeString()}</td>
                    <td>{item.seller}</td>
                    <td>{item.provider_conversation_id}</td>
                    <td>{item.buyer}</td>
                    <td>{item.agent}</td>
                    <td>{item.category}</td>
                    <td>{item.subcategory || '-'}</td>
                    <td>{item.message_preview}</td>
                    <td>{item.conversation_message_id}</td>
                    <td>
                      <a className="icon-button" href={`/inbox?conversation_id=${encodeURIComponent(item.conversation_id)}`} title="Go to Conversation" aria-label="Go to Conversation">
                        <Icon name="message" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </AppLayout>
  )
}

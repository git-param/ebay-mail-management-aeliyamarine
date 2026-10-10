import { useState } from 'react'
import { fetchConversationAdditionalDetails } from '../../../services/conversationApi'

function displayValue(value) {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value)) return value
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function AdditionalDetailsPanel({ conversationId }) {
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [error, setError] = useState('')

  async function loadDetails(refresh = false) {
    if (data && !refresh) {
      setIsOpen((open) => !open)
      return
    }
    setIsLoading(true)
    setError('')
    try {
      setData(await fetchConversationAdditionalDetails(conversationId))
      setIsOpen(true)
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to load additional details.')
    } finally {
      setIsLoading(false)
    }
  }

  const orders = (data?.orders || []).filter((order) => order.sections?.length)

  return (
    <section className="detail-section additional-details-panel">
      <button className="secondary-button additional-details-toggle" type="button"
        onClick={() => loadDetails()} disabled={isLoading} aria-expanded={isOpen}
        aria-controls={`additional-details-${conversationId}`}>
        {isLoading ? 'Loading details…' : isOpen ? 'Hide additional details' : 'Load more details'}
      </button>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      <div id={`additional-details-${conversationId}`} hidden={!isOpen} aria-busy={isLoading}>
        {data ? (
          <button className="secondary-button compact-action" type="button"
            disabled={isLoading} onClick={() => loadDetails(true)}>
            {isLoading ? 'Refreshing…' : 'Refresh details'}
          </button>
        ) : null}
        {data && !orders.length ? <p className="detail-muted">No additional buyer or order details found.</p> : null}
        {orders.map((order) => (
          <div className="additional-order-details" key={order.order_id}>
            <h3>Order {order.order_id}</h3>
            {orders.length > 1 ? <p className="detail-muted">Matching buyer order</p> : null}
            {order.sections.map((section) => (
              <section key={section.title} className="additional-details-group">
                <h4>{section.title}</h4>
                <dl className="metadata-list">
                  {section.rows.map((row) => (
                    <div key={row.label}><dt>{row.label}</dt><dd>{displayValue(row.value)}</dd></div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}

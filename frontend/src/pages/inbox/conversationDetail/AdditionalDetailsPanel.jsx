import { useState } from 'react'
import { Icon } from '../../../layouts/app_layout'
import { fetchConversationAdditionalDetails } from '../../../services/conversationApi'
import AdditionalOrderDetails from './AdditionalOrderDetails'
import './additionalDetails.css'

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
      <div className="additional-details-toolbar">
        <div className="additional-details-heading">
          <span className="additional-details-heading-icon"><Icon name="package" /></span>
          <div><h3>Buyer &amp; order details</h3><p>Contacts, delivery &amp; payments</p></div>
        </div>
        {data ? (
          <button className="additional-details-icon-button" type="button"
            disabled={isLoading} onClick={() => loadDetails(true)}
            title="Refresh details" aria-label="Refresh buyer and order details">
            <Icon name="refresh" />
          </button>
        ) : null}
      </div>
      <button className="secondary-button additional-details-toggle" type="button"
        onClick={() => loadDetails()} disabled={isLoading} aria-expanded={isOpen}
        aria-controls={`additional-details-${conversationId}`}>
        <span>{isLoading ? 'Loading details…' : isOpen ? 'Hide details' : 'Load more details'}</span>
        <span className={`additional-details-chevron ${isOpen ? 'expanded' : ''}`} aria-hidden="true" />
      </button>
      {error ? <p className="form-message error" role="alert">{error}</p> : null}
      <div id={`additional-details-${conversationId}`} hidden={!isOpen} aria-busy={isLoading}>
        {data && !orders.length ? <p className="additional-details-empty" role="status">No additional buyer or order details found.</p> : null}
        {orders.map((order) => (
          <AdditionalOrderDetails order={order} key={order.order_id} />
        ))}
      </div>
    </section>
  )
}

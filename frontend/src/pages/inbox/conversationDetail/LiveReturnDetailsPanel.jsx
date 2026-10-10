import { useState } from 'react'
import { Icon } from '../../../layouts/app_layout'
import { fetchConversationLiveReturns } from '../../../services/conversationApi'
import AdditionalOrderDetails from './AdditionalOrderDetails'
import './additionalDetails.css'

export default function LiveReturnDetailsPanel({ detail }) {
  const selected = detail.order_context?.selected_order
  const orders = selected ? [selected] : detail.order_context?.candidate_orders || []
  const [orderRecordId, setOrderRecordId] = useState(selected?.id || orders[0]?.id || '')
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  async function fetchReturns(loadMore = false) {
    if (isLoading) return
    setIsLoading(true)
    setError('')
    try {
      const result = await fetchConversationLiveReturns(detail.id, {
        order_record_id: orderRecordId || undefined,
        offset: loadMore ? data.next_offset : 0,
      })
      setData((current) => loadMore && current
        ? { ...result, returns: [...current.returns, ...result.returns.filter(
          (item) => !current.returns.some((existing) => existing.return_id === item.return_id),
        )] }
        : result)
    } catch (caughtError) {
      setError(caughtError.message || 'Unable to fetch return details from eBay.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="detail-section additional-details-panel live-returns-panel" aria-label="Live eBay returns">
      <div className="additional-details-toolbar">
        <div className="additional-details-heading">
          <span className="additional-details-heading-icon"><Icon name="package" /></span>
          <div><h3>Returns &amp; refunds</h3><p>Fetch the latest details from eBay</p></div>
        </div>
        <span className="live-returns-source">eBay</span>
      </div>
      {orders.length > 1 ? (
        <label className="live-returns-order-select">Order
          <select value={orderRecordId} disabled={isLoading} onChange={(event) => {
            setOrderRecordId(event.target.value)
            setData(null)
            setError('')
          }}>
            {orders.map((order) => <option key={order.id} value={order.id}>{order.order_id}</option>)}
          </select>
        </label>
      ) : null}
      <button className="secondary-button additional-details-toggle" type="button"
        disabled={isLoading} onClick={() => fetchReturns()} aria-controls={`live-returns-${detail.id}`}>
        <span>{isLoading ? 'Fetching from eBay…' : 'Fetch return details'}</span>
        <Icon name="refresh" />
      </button>
      {error ? <p className="form-message error live-returns-error" role="alert">{error}</p> : null}
      <div id={`live-returns-${detail.id}`} aria-busy={isLoading}>
        {data ? (
          <>
            <p className="live-returns-fetched" role="status">
              {data.returns.length} {data.returns.length === 1 ? 'return' : 'returns'} · Fetched {new Date(data.fetched_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
            </p>
            {!data.returns.length ? (
              <p className="additional-details-empty">eBay found no returns for order {data.order_id}.</p>
            ) : data.returns.map((returned) => (
              <div className="live-return-result" key={returned.return_id}>
                <h4>Return #{returned.return_id}</h4>
                {returned.warning ? <p className="live-returns-warning">{returned.warning}</p> : null}
                <AdditionalOrderDetails order={{ order_id: returned.order_id, sections: returned.sections }} />
              </div>
            ))}
            {data.next_offset !== null ? (
              <button className="secondary-button additional-details-toggle" type="button"
                disabled={isLoading} onClick={() => fetchReturns(true)}>Load more returns</button>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  )
}

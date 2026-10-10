import { Icon } from '../../../layouts/app_layout'

function displayValue(value) {
  const money = /^(-?\d+(?:\.\d+)?) ([A-Z]{3})$/.exec(value)
  if (money) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency', currency: money[2], currencyDisplay: 'code',
      }).format(Number(money[1]))
    } catch { /* Keep the stored amount if its currency is unsupported. */ }
  }
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
      })
    }
  }
  return value
}

function sectionIcon(title) {
  if (/buyer|recipient/i.test(title)) return 'users'
  if (/delivery/i.test(title)) return 'clock'
  if (/payment|refund|totals/i.test(title)) return 'tag'
  return 'package'
}

function statusTone(value) {
  if (/^(PAID|SUCCEEDED|COMPLETED|FULFILLED|CLOSED|REFUNDED)$/.test(value)) return 'success'
  if (/FAILED|REJECTED|CANCELLED/.test(value)) return 'danger'
  return 'neutral'
}

function DetailValue({ row }) {
  const isStatus = /status|state|fulfillment/i.test(row.label)
  const value = displayValue(row.value)
  return isStatus ? (
    <span className={`additional-status-badge ${statusTone(row.value)}`}>
      {value.replaceAll('_', ' ')}
    </span>
  ) : value
}

export default function AdditionalOrderDetails({ order }) {
  return (
    <article className="additional-order-details" aria-label={`Details for order ${order.order_id}`}>
      <header className="additional-order-heading">
        <span>ORDER</span><strong>{order.order_id}</strong>
      </header>
      <div className="additional-details-cards">
        {order.sections.map((section) => (
          <details key={section.title} className="additional-details-card"
            open={/^(Order|Buyer registration|Refund|Return)/.test(section.title) && !/^Order item/.test(section.title)}>
            <summary>
              <span className="additional-card-icon"><Icon name={sectionIcon(section.title)} /></span>
              <span>{section.title}</span>
              <span className="additional-details-chevron" aria-hidden="true" />
            </summary>
            <dl className="additional-details-fields">
              {section.rows.map((row) => (
                <div key={row.label} className={/^(Address|Email|Title)$/.test(row.label) ? 'stacked' : ''}>
                  <dt>{row.label}</dt>
                  <dd><DetailValue row={row} /></dd>
                </div>
              ))}
            </dl>
          </details>
        ))}
      </div>
    </article>
  )
}

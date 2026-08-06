import {
  formatCurrency,
  formatDate,
  getOfferLabel,
  offerTimestamp,
} from '../inboxUtils'

function OfferEvent({
  offer,
  conversation,
}) {
  const direction = String(
    offer?.direction || '',
  ).toUpperCase()

  const offerType = String(
    offer?.offer_type ||
    offer?.type ||
    '',
  ).toUpperCase()

  const status = String(
    offer?.status || '',
  ).toUpperCase()

  const isAccepted =
    status === 'ACCEPTED' ||
    offerType.includes('ACCEPTED')

  const isOutgoing =
    !isAccepted &&
    [
      'OUTGOING',
      'SELLER_TO_BUYER',
    ].includes(direction)

  const isIncoming =
    isAccepted ||
    [
      'INCOMING',
      'BUYER_TO_SELLER',
    ].includes(direction)

  const isNeutral =
    !isOutgoing && !isIncoming

  const isExpired =
    status === 'EXPIRED'

  const isDeclined =
    status === 'DECLINED'

  const buyerName =
    offer?.buyer_username ||
    conversation?.buyer_identifier ||
    'Buyer'

  const label = isExpired
    ? 'Offer expired'
    : isDeclined
      ? 'Offer declined'
      : getOfferLabel(
          offer,
          isOutgoing,
          buyerName,
        )

  const rawAmount =
    offer?.offer_amount ??
    offer?.amount

  const amountNumber =
    rawAmount == null
      ? null
      : Number(rawAmount)

  const amount =
    amountNumber == null ||
    Number.isNaN(amountNumber)
      ? ''
      : formatCurrency(
          amountNumber,
          offer?.currency || 'USD',
        )

  const sellerOfferMessage = isOutgoing
    ? String(
        offer?.raw_text ||
        offer?.rawText ||
        '',
      ).trim()
    : ''

  const avatarLabel = String(
    buyerName || 'B',
  )
    .slice(0, 1)
    .toUpperCase()

  const rowClassName = [
    'offer-chat-row',
    isOutgoing
      ? 'offer-chat-row-outgoing'
      : '',
    isIncoming
      ? 'offer-chat-row-incoming'
      : '',
    isNeutral
      ? 'offer-chat-row-neutral'
      : '',
  ]
    .filter(Boolean)
    .join(' ')

  const cardClassName = [
    'offer-chat-card',
    isOutgoing
      ? 'offer-chat-card-outgoing'
      : 'offer-chat-card-incoming',
    isAccepted
      ? 'offer-chat-card-accepted'
      : '',
    isExpired
      ? 'offer-chat-card-expired'
      : '',
    isDeclined
      ? 'offer-chat-card-declined'
      : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <>
      {sellerOfferMessage ? (
        <div className="offer-seller-message-row">
          <div className="offer-seller-message-bubble">
            {sellerOfferMessage}
          </div>
        </div>
      ) : null}

      <div className={rowClassName}>
        {isIncoming ? (
          <div
            className={`offer-avatar ${
              isAccepted
                ? 'offer-avatar-accepted'
                : ''
            }`}
            aria-hidden="true"
          >
            {isAccepted ? (
              <span className="offer-check-mark" />
            ) : (
              avatarLabel
            )}
          </div>
        ) : null}

        <div>
          <article className={cardClassName}>
            <span className="offer-chat-label">
              {label}
            </span>

            {amount ? (
              <strong className="offer-chat-amount">
                {amount}
              </strong>
            ) : null}

            {status &&
            status !== 'PENDING' ? (
              <small className="offer-chat-status">
                {status}
              </small>
            ) : null}
          </article>

          <time className="offer-chat-time">
            {formatDate(
              offerTimestamp(offer),
            )}
          </time>
        </div>
      </div>
    </>
  )
}

export default OfferEvent
import {
  formatCurrency,
  formatDate,
  getOfferLabel,
  offerTimestamp,
} from '../inboxUtils'

function OfferEvent({
  offer,
  conversation,
  showSellerMessage = true,
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

  const isExpired =
    status === 'EXPIRED'

  const isDeclined =
    status === 'DECLINED'

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
    !isOutgoing &&
    !isIncoming

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

  /*
   * Offer notifications can include both buyer and seller notes.
   * Status-only records should not repeat fallback raw_text from an earlier
   * active offer, but explicit provider-side messages are still shown.
   */
  const shouldShowSellerMessage =
    showSellerMessage &&
    !isExpired &&
    !isDeclined &&
    !isAccepted

  const explicitSellerMessage = String(
    offer?.seller_message ||
      offer?.sellerMessage ||
      '',
  ).trim()

  const explicitBuyerMessage = String(
    offer?.buyer_message ||
      offer?.buyerMessage ||
      '',
  ).trim()

  const legacyRawText = String(
    offer?.raw_text ||
      offer?.rawText ||
      '',
  ).trim()

  const sellerOfferMessage = (
    explicitSellerMessage ||
    (
      shouldShowSellerMessage &&
      isOutgoing
        ? legacyRawText
        : ''
    )
  )

  const buyerOfferMessage = (
    explicitBuyerMessage ||
    (
      isIncoming &&
      !explicitSellerMessage
        ? legacyRawText
        : ''
    )
  )

  const showBuyerOfferMessage = (
    buyerOfferMessage &&
    buyerOfferMessage !== sellerOfferMessage
  )

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

      {showBuyerOfferMessage ? (
        <div className="offer-buyer-message-row">
          <div className="offer-buyer-message-bubble">
            {buyerOfferMessage}
          </div>
        </div>
      ) : null}

      <div className={rowClassName}>
        {isIncoming ? (
          <div
            className={[
              'offer-avatar',

              isAccepted
                ? 'offer-avatar-accepted'
                : '',
            ]
              .filter(Boolean)
              .join(' ')}
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

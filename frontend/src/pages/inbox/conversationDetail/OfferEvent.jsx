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
  visibleMessageBodies = [],
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
   * Offer rows can carry notes copied from another event in the same offer
   * sequence. A seller note belongs only to a seller-originated event, and a
   * buyer note belongs only to a buyer-originated event. Terminal status rows
   * (accepted / expired / declined) should never replay an earlier note.
   */
  const isTerminalStatus =
    isAccepted ||
    isExpired ||
    isDeclined

  const sellerOriginated =
    isOutgoing ||
    offerType.includes('SELLER')

  const buyerOriginated =
    isIncoming ||
    offerType.includes('BUYER')

  const canShowSellerMessage =
    showSellerMessage &&
    sellerOriginated &&
    !isTerminalStatus

  const canShowBuyerMessage =
    buyerOriginated &&
    !isTerminalStatus

  const legacyRawText = String(
    offer?.raw_text ||
      offer?.rawText ||
      '',
  ).trim()

  const normalizeMessageText = (value) =>
    String(value || '')
      .trim()
      .replace(/\s+/g, ' ')

  const normalizedVisibleBodies =
    new Set(
      visibleMessageBodies
        .map(normalizeMessageText)
        .filter(Boolean),
    )

  function isAlreadyVisibleMessage(value) {
    const normalizedValue =
      normalizeMessageText(value)

    return (
      normalizedValue &&
      normalizedVisibleBodies.has(
        normalizedValue,
      )
    )
  }

  /*
   * raw_text is overloaded by the backend: sometimes it is a real buyer/
   * seller note and sometimes it is an eBay event sentence. Do not turn an
   * event sentence into a chat bubble.
   */
  function isOfferEventText(value) {
    const normalizedValue =
      normalizeMessageText(value)
        .toLowerCase()

    if (!normalizedValue) {
      return false
    }

    return [
      'counteroffer submitted to buyer',
      'you sent an offer',
      'you sent a counteroffer',
      'buyer sent an offer',
      'buyer made a counteroffer',
      'you have a new offer',
      'accepted an offer',
      'accepted your offer',
      'offer accepted',
      'offer declined',
      'offer expired',
      'counteroffer accepted',
      'counteroffer declined',
      'counteroffer expired',
    ].some((phrase) =>
      normalizedValue.includes(phrase),
    )
  }

  const rawSellerMessage = String(
    offer?.seller_message ||
      offer?.sellerMessage ||
      '',
  ).trim()

  const rawBuyerMessage = String(
    offer?.buyer_message ||
      offer?.buyerMessage ||
      '',
  ).trim()

  const explicitSellerMessage =
    canShowSellerMessage &&
    rawSellerMessage &&
    !isAlreadyVisibleMessage(
      rawSellerMessage,
    )
      ? rawSellerMessage
      : ''

  const explicitBuyerMessage =
    canShowBuyerMessage &&
    rawBuyerMessage &&
    !isAlreadyVisibleMessage(
      rawBuyerMessage,
    )
      ? rawBuyerMessage
      : ''

  const canUseLegacyRawText =
    legacyRawText &&
    !isOfferEventText(legacyRawText) &&
    !isAlreadyVisibleMessage(
      legacyRawText,
    )

  const sellerOfferMessage =
    explicitSellerMessage ||
    (
      canShowSellerMessage &&
      canUseLegacyRawText
        ? legacyRawText
        : ''
    )

  const buyerOfferMessage =
    explicitBuyerMessage ||
    (
      canShowBuyerMessage &&
      canUseLegacyRawText &&
      legacyRawText !==
        sellerOfferMessage
        ? legacyRawText
        : ''
    )

  const showBuyerOfferMessage =
    Boolean(
      buyerOfferMessage &&
      buyerOfferMessage !==
        sellerOfferMessage,
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
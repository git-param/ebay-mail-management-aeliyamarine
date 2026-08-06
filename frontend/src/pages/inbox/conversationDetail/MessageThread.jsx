import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  translateMessage,
} from '../../../services/conversationApi'
import { EmptyPanel } from '../conversationList/ConversationList'
import {
  SHOW_MESSAGE_ATTACHMENTS,
  eventTimeValue,
  formatDate,
  isEbayNotificationMessage,
  isHtmlBody,
  isImageAttachment,
  offerTimestamp,
} from '../inboxUtils'
import OfferEvent from './OfferEvent'

function resizeEbayMessageFrame(event) {
  const frame = event.currentTarget
  const documentElement =
    frame.contentDocument?.documentElement
  const body =
    frame.contentDocument?.body

  if (!documentElement || !body) {
    return
  }

  const frameHeight = Math.max(
    documentElement.scrollHeight,
    body.scrollHeight,
    160,
  )

  frame.style.height = `${frameHeight}px`
}

function AttachmentList({
  attachments = [],
}) {
  if (
    !SHOW_MESSAGE_ATTACHMENTS ||
    !attachments.length
  ) {
    return null
  }

  return (
    <div className="message-attachments">
      {attachments.map(
        (attachment, index) => {
          const attachmentUrl =
            attachment.media_url ||
            attachment.download_url ||
            ''

          const attachmentName =
            attachment.media_name ||
            attachment.file_name ||
            `Attachment ${index + 1}`

          const imageAttachment =
            attachmentUrl &&
            isImageAttachment(attachment)

          const attachmentKey =
            attachment.id ||
            `${attachmentName}-${index}`

          return (
            <div
              className={[
                'attachment-card',
                imageAttachment
                  ? 'attachment-card-image'
                  : '',
              ]
                .filter(Boolean)
                .join(' ')}
              key={attachmentKey}
            >
              {imageAttachment ? (
                <a
                  className="attachment-preview"
                  href={attachmentUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Open ${attachmentName}`}
                >
                  <img
                    src={attachmentUrl}
                    alt={attachmentName}
                    loading="lazy"
                  />
                </a>
              ) : (
                <div>
                  <strong>
                    {attachmentName}
                  </strong>

                  {attachment.file_size ? (
                    <small>
                      {Math.round(
                        attachment.file_size /
                          1024,
                      )}{' '}
                      KB
                    </small>
                  ) : null}

                  {!attachmentUrl ? (
                    <small>
                      Attachment URL unavailable
                    </small>
                  ) : null}

                  {attachmentUrl ? (
                    <a
                      href={attachmentUrl}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open attachment
                    </a>
                  ) : null}
                </div>
              )}
            </div>
          )
        },
      )}
    </div>
  )
}

function MessageTranslation({
  message,
  translation,
  isTranslating,
  onTranslate,
}) {
  if (!message.body) {
    return null
  }

  return (
    <div className="message-translation">
      <button
        className="translation-button"
        type="button"
        disabled={isTranslating}
        onClick={() =>
          onTranslate(message)
        }
      >
        {isTranslating
          ? 'Translating…'
          : 'Translate to English'}
      </button>

      {translation?.text ? (
        <p className="translated-copy">
          <strong>English:</strong>{' '}
          {translation.text}
        </p>
      ) : null}

      {translation?.error ? (
        <small role="alert">
          {translation.error}
        </small>
      ) : null}
    </div>
  )
}

function getMessageTimestamp(message) {
  return (
    message?.sent_at ||
    message?.created_date ||
    message?.created_at ||
    message?.updated_at ||
    null
  )
}

function getOfferTimestampValue(offer) {
  return (
    offer?.event_timestamp ||
    offer?.event_time ||
    offer?.occurred_at ||
    offer?.offer_date ||
    offer?.sent_at ||
    offerTimestamp(offer) ||
    offer?.created_at ||
    offer?.created_date ||
    offer?.updated_at ||
    null
  )
}

function getOfferMessageId(offer) {
  return (
    offer?.message_id ||
    offer?.messageId ||
    offer?.source_message_id ||
    null
  )
}

function getOfferUniqueKey(
  offer,
  sourceMessage = null,
) {
  const providerId =
    offer?.provider_offer_id ||
    offer?.offer_id ||
    offer?.id

  if (providerId) {
    return `provider:${providerId}`
  }

  return [
    'offer',
    getOfferMessageId(offer) ||
      sourceMessage?.id ||
      'unlinked',
    offer?.offer_type ||
      offer?.type ||
      '',
    offer?.direction || '',
    offer?.status || '',
    offer?.offer_amount ??
      offer?.amount ??
      '',
    getOfferTimestampValue(offer) ||
      getMessageTimestamp(
        sourceMessage,
      ) ||
      '',
  ].join(':')
}

function normalizeOffer(
  offer,
  sourceMessage,
  conversation,
) {
  const timestamp =
    getOfferTimestampValue(offer) ||
    getMessageTimestamp(
      sourceMessage,
    )

  return {
    ...offer,

    id:
      offer?.id ||
      `offer-${getOfferUniqueKey(
        offer,
        sourceMessage,
      )}`,

    message_id:
      getOfferMessageId(offer) ||
      sourceMessage?.id ||
      null,

    created_at: timestamp,

    created_date:
      offer?.created_date ||
      timestamp,

    buyer_username:
      offer?.buyer_username ||
      conversation?.buyer_identifier ||
      sourceMessage?.sender_identifier ||
      'Buyer',
  }
}

function collectStructuredOffers(
  messages,
  offers,
  conversation,
) {
  const collected = []
  const seen = new Set()

  function addOffer(
    offer,
    sourceMessage = null,
  ) {
    if (!offer) {
      return
    }

    const uniqueKey =
      getOfferUniqueKey(
        offer,
        sourceMessage,
      )

    if (seen.has(uniqueKey)) {
      return
    }

    seen.add(uniqueKey)

    collected.push(
      normalizeOffer(
        offer,
        sourceMessage,
        conversation,
      ),
    )
  }

  ;(offers || []).forEach(
    (offer) => addOffer(offer),
  )

  ;(messages || []).forEach(
    (message) => {
      const messageOffers = [
        ...(Array.isArray(
          message.offers,
        )
          ? message.offers
          : []),

        ...(message.offer
          ? [message.offer]
          : []),

        ...(message.structured_offer
          ? [
              message.structured_offer,
            ]
          : []),
      ]

      messageOffers.forEach(
        (offer) =>
          addOffer(
            offer,
            message,
          ),
      )
    },
  )

  return collected
}

function isOfferNotificationMessage(
  message,
  structuredOffers,
) {
  if (
    message?.is_offer_notification
  ) {
    return true
  }

  const messageId = message?.id

  if (
    messageId &&
    structuredOffers.some(
      (offer) =>
        offer.message_id ===
        messageId,
    )
  ) {
    return true
  }

  const body = String(
    message?.body ||
      message?.message ||
      message?.text ||
      '',
  ).toLowerCase()

  const subject = String(
    message?.subject || '',
  ).toLowerCase()

  const combined =
    `${subject} ${body}`

  const looksLikeOfferNotification =
    combined.includes(
      'sent an offer',
    ) ||
    combined.includes(
      'sent a counteroffer',
    ) ||
    combined.includes(
      'accepted an offer',
    ) ||
    combined.includes(
      'offer accepted',
    ) ||
    combined.includes(
      'offer declined',
    ) ||
    combined.includes(
      'offer expired',
    )

  return (
    looksLikeOfferNotification &&
    structuredOffers.length > 0
  )
}

function buildTimelineItems(
  messages,
  structuredOffers,
) {
  const timeline = []

  messages.forEach(
    (message, index) => {
      if (
        isOfferNotificationMessage(
          message,
          structuredOffers,
        )
      ) {
        return
      }

      timeline.push({
        key:
          message.id ||
          `message-${index}`,

        type: 'message',
        message,
        timestamp:
          getMessageTimestamp(
            message,
          ),
        originalIndex: index,
      })
    },
  )

  structuredOffers.forEach(
    (offer, index) => {
      timeline.push({
        key:
          offer.provider_offer_id ||
          offer.offer_id ||
          offer.id ||
          `offer-${index}`,

        type: 'offer',
        offer,
        timestamp:
          getOfferTimestampValue(
            offer,
          ),
        originalIndex: index,
      })
    },
  )

  return timeline.sort(
    (left, right) => {
      const leftTime =
        eventTimeValue(
          left.timestamp,
        )

      const rightTime =
        eventTimeValue(
          right.timestamp,
        )

      if (
        leftTime !== rightTime
      ) {
        return leftTime - rightTime
      }

      /*
       * When an offer and message have exactly
       * the same timestamp, show the message
       * first and then the structured event.
       */
      if (
        left.type !== right.type
      ) {
        return left.type ===
          'message'
          ? -1
          : 1
      }

      return (
        left.originalIndex -
        right.originalIndex
      )
    },
  )
}

function MessageThread({
  messages = [],
  offers = [],
  isSystemConversation,
  conversation,
}) {
  const threadRef = useRef(null)

  const [translations, setTranslations] =
    useState({})

  const [
    translatingId,
    setTranslatingId,
  ] = useState(null)

  const translateBuyerMessage =
    useCallback(async (message) => {
      if (!message?.id || !message.body) {
        return
      }

      setTranslatingId(message.id)

      try {
        const result =
          await translateMessage(
            message.body,
            'en',
          )

        setTranslations((current) => ({
          ...current,

          [message.id]: {
            text:
              result.translated_text ||
              result.translation ||
              '',
          },
        }))
      } catch (error) {
        setTranslations((current) => ({
          ...current,

          [message.id]: {
            error:
              error.message ||
              'Translation failed.',
          },
        }))
      } finally {
        setTranslatingId(null)
      }
    }, [])

  useLayoutEffect(() => {
    const thread =
      threadRef.current

    if (!thread) {
      return
    }

    thread.scrollTop =
      thread.scrollHeight
  }, [
    conversation?.id,
    messages.length,
    offers.length,
  ])

  /*
   * Preserve the original dashboard logic:
   *
   * Offers linked to a message are rendered in place
   * of that source message.
   *
   * They do not enter the independent offer timeline.
   */
  const offersByMessageId =
    useMemo(() => {
      const grouped = new Map()

      if (
        isSystemConversation ||
        conversation
          ?.provider_conversation_type ===
          'FROM_EBAY'
      ) {
        return grouped
      }

      function addOffer(
        messageId,
        offer,
      ) {
        if (!messageId || !offer) {
          return
        }

        const current =
          grouped.get(messageId) || []

        grouped.set(messageId, [
          ...current,
          offer,
        ])
      }

      ;(offers || []).forEach(
        (offer) => {
          addOffer(
            offer.message_id ||
              offer.messageId ||
              offer.source_message_id,
            offer,
          )
        },
      )

      return grouped
    }, [
      offers,
      conversation,
      isSystemConversation,
    ])

  /*
   * Normalize and deduplicate all structured offers.
   * This mirrors the original dashboard implementation.
   */
  const structuredOffers =
    useMemo(() => {
      if (
        isSystemConversation ||
        conversation
          ?.provider_conversation_type ===
          'FROM_EBAY'
      ) {
        return []
      }

      const seen = new Set()
      const items = []

      function addOffer(
        offer,
        sourceMessage = null,
      ) {
        if (!offer) {
          return
        }

        const key = String(
          offer.provider_offer_id ||
            offer.id ||
            `${
              sourceMessage?.id ||
              'top'
            }:${
              offer.offer_amount ||
              offer.amount
            }:${
              offer.status
            }:${
              offer.direction
            }:${
              offerTimestamp(
                offer,
              ) ||
              sourceMessage
                ?.sent_at ||
              ''
            }`,
        )

        if (seen.has(key)) {
          return
        }

        seen.add(key)

        const normalizedTimestamp =
          offerTimestamp(offer) ||
          sourceMessage?.sent_at ||
          sourceMessage?.created_at ||
          sourceMessage?.created_date

        items.push({
          ...offer,

          id:
            offer.id ||
            `offer-${key}`,

          message_id:
            offer.message_id ||
            offer.messageId ||
            offer.source_message_id ||
            sourceMessage?.id,

          created_at:
            normalizedTimestamp,

          created_date:
            offer.created_date ||
            normalizedTimestamp,

          buyer_username:
            offer.buyer_username ||
            conversation
              ?.buyer_identifier ||
            sourceMessage
              ?.sender_identifier,
        })
      }

      ;(offers || []).forEach(
        (offer) =>
          addOffer(offer),
      )

      return items
    }, [
      offers,
      conversation,
      isSystemConversation,
    ])

  /*
   * Only offers that do not belong to a stored message
   * are added independently to timelineItems.
   */
  const unlinkedStructuredOffers =
    useMemo(() => {
      const messageIds = new Set(
        messages.map(
          (message) => message.id,
        ),
      )

      return structuredOffers.filter(
        (offer) =>
          !offer.message_id ||
          !messageIds.has(
            offer.message_id,
          ),
      )
    }, [
      structuredOffers,
      messages,
    ])

  /*
   * Original timeline:
   * - all messages
   * - only unlinked structured offers
   *
   * Linked offer cards remain at their source
   * message's position.
   */
  const timelineItems =
    useMemo(() => {
      const items = [
        ...messages.map(
          (message, index) => ({
            type: 'message',
            message,
            index,

            timestamp:
              message.sent_at ||
              message.created_at ||
              message.created_date,
          }),
        ),

        ...unlinkedStructuredOffers.map(
          (offer, index) => ({
            type: 'offer',
            offer,
            index,

            timestamp:
              offerTimestamp(offer),
          }),
        ),
      ]

      return items.sort(
        (left, right) => {
          const difference =
            eventTimeValue(
              left.timestamp,
            ) -
            eventTimeValue(
              right.timestamp,
            )

          if (difference !== 0) {
            return difference
          }

          /*
           * Preserve original tie behavior:
           * offer before message when timestamps match.
           */
          if (
            left.type !== right.type
          ) {
            return left.type ===
              'offer'
              ? -1
              : 1
          }

          return (
            left.index -
            right.index
          )
        },
      )
    }, [
      messages,
      unlinkedStructuredOffers,
    ])

  if (
    !messages.length &&
    !structuredOffers.length
  ) {
    return (
      <EmptyPanel
        title="No messages yet"
        message="This conversation has no stored message bodies."
      />
    )
  }

  return (
    <div
      className="message-thread"
      ref={threadRef}
    >
      {timelineItems.map(
        (item) => {
          /*
           * Independently stored offer with no matching
           * message record.
           */
          if (
            item.type === 'offer'
          ) {
            const offer =
              item.offer

            return (
              <div
                className="offer-message-slot"
                key={`unlinked-offer-${
                  offer
                    .provider_offer_id ||
                  offer.id ||
                  item.index
                }`}
              >
                <OfferEvent
                  offer={offer}
                  conversation={
                    conversation
                  }
                />
              </div>
            )
          }

          const {
            message,
            index,
          } = item

          /*
           * Look for structured offers linked to this
           * exact message.
           */
          const messageOffers =
            offersByMessageId.get(
              message.id,
            ) || []

          /*
          * A single source message can have multiple offer-state
          * records. Keep the message's timeline position, but order
          * those records using their true provider timestamps.
          */
          const displayOffers = [
            ...messageOffers,
          ].sort((left, right) => {
            const leftTime =
              eventTimeValue(
                offerTimestamp(left),
              )

            const rightTime =
              eventTimeValue(
                offerTimestamp(right),
              )

            if (leftTime !== rightTime) {
              return leftTime - rightTime
            }

            /*
            * Stable logical order when the API timestamps
            * are identical or unavailable.
            */
            const statusOrder = {
              PENDING: 1,
              ACCEPTED: 2,
              DECLINED: 2,
              EXPIRED: 3,
            }

            const leftStatus =
              String(
                left.status || 'PENDING',
              ).toUpperCase()

            const rightStatus =
              String(
                right.status || 'PENDING',
              ).toUpperCase()

            return (
              (statusOrder[leftStatus] || 1) -
              (statusOrder[rightStatus] || 1)
            )
          })

          const isOfferNotification =
            displayOffers.length > 0

          const isSystem =
            isEbayNotificationMessage(
              message,
            )

          const direction =
            isSystem
              ? 'system'
              : message.is_inbound
                ? 'inbound'
                : 'outbound'

          const isSeller =
            direction === 'outbound'

          /*
           * Backend marked this as an offer notification,
           * but no structured offer was returned.
           *
           * Original code hides the raw notification.
           */
          if (
            message
              .is_offer_notification &&
            !displayOffers.length
          ) {
            return null
          }

          /*
           * Replace the raw message with one or more
           * structured eBay-style offer cards.
           *
           * Most importantly, the source MESSAGE timestamp
           * is used before the offer timestamp.
           */
          if (isOfferNotification) {
            return (
              <div
                className="offer-message-slot"
                key={
                  message.id ||
                  index
                }
              >
                {displayOffers.map(
                  (
                    offer,
                    offerIndex,
                  ) => {
                    const providerTimestamp =
                      offerTimestamp(offer)

                    const messageTimestamp =
                      message.sent_at ||
                      message.created_at ||
                      message.created_date

                    return (
                      <OfferEvent
                        offer={{
                          ...offer,

                          /*
                          * Keep the real offer/provider timestamp.
                          * Use the message timestamp only as fallback.
                          */
                          created_at:
                            providerTimestamp ||
                            messageTimestamp,

                          created_date:
                            providerTimestamp ||
                            offer.created_date ||
                            messageTimestamp,

                          buyer_username:
                            offer.buyer_username ||
                            conversation
                              ?.buyer_identifier ||
                            message
                              .sender_identifier,
                        }}
                        /*
                        * Only one active outgoing event should render
                        * the seller text. Status-only records should not.
                        */
                        showSellerMessage={
                          offerIndex === 0 ||
                          String(
                            offer.status || '',
                          ).toUpperCase() ===
                            'PENDING'
                        }
                        key={`offer-${
                          offer.provider_offer_id ||
                          offer.id ||
                          message.id
                        }-${offerIndex}`}
                        conversation={
                          conversation
                        }
                      />
                    )
                  },
                )}
              </div>
            )
          }

          const messageBody =
            message.body ||
            message.message ||
            message.text ||
            ''

          const hasBody =
            Boolean(messageBody)

          const attachments =
            message.attachments || []

          const hasOnlyImageAttachments =
            !hasBody &&
            attachments.length > 0 &&
            attachments.every(
              isImageAttachment,
            )

          const bubbleClassName = [
            'message-bubble',
            direction,

            hasOnlyImageAttachments
              ? 'image-attachment-message'
              : '',
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <article
              className={
                bubbleClassName
              }
              key={
                message.id ||
                index
              }
            >
              <div className="message-meta">
                <strong>
                  {direction ===
                  'system'
                    ? 'eBay notification'
                    : isSeller
                      ? 'You'
                      : message
                          .sender_identifier ||
                        message
                          .sender_type ||
                        'Buyer'}
                </strong>

                <time>
                  {formatDate(
                    message.sent_at ||
                      message
                        .created_date,
                  )}
                </time>
              </div>

              {hasOnlyImageAttachments ? null : isSystemConversation &&
                isHtmlBody(
                  message.body,
                ) ? (
                <iframe
                  className="ebay-html-message"
                  title={`eBay message ${
                    message.id ||
                    index
                  }`}
                  srcDoc={
                    message.body
                  }
                  sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
                  scrolling="no"
                  onLoad={
                    resizeEbayMessageFrame
                  }
                />
              ) : (
                <p>{messageBody}</p>
              )}

              {direction ===
                'inbound' &&
              message.body ? (
                <MessageTranslation
                  message={message}
                  translation={
                    translations[
                      message.id
                    ]
                  }
                  isTranslating={
                    translatingId ===
                    message.id
                  }
                  onTranslate={
                    translateBuyerMessage
                  }
                />
              ) : null}

              <AttachmentList
                attachments={
                  attachments
                }
              />

              {message.read_status !==
                undefined &&
              message.read_status !==
                null ? (
                <span className="message-status">
                  {message.read_status
                    ? '✓ Read'
                    : '● Unread'}
                </span>
              ) : null}
            </article>
          )
        },
      )}
    </div>
  )
}

export {
  AttachmentList,
  MessageTranslation,
  buildTimelineItems,
  collectStructuredOffers,
  getMessageTimestamp,
  getOfferTimestampValue,
  resizeEbayMessageFrame,
}

export default MessageThread
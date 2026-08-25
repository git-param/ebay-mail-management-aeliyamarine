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
  onToggleOriginal,
}) {
  if (!message.body) {
    return null
  }

  const hasTranslation =
    Boolean(translation?.text)

  return (
    <div className="message-translation">
      <button
        className="translation-button"
        type="button"
        disabled={isTranslating}
        onClick={() => {
          if (hasTranslation) {
            onToggleOriginal(message.id)
            return
          }

          onTranslate(message)
        }}
      >
        {isTranslating
          ? 'Translating…'
          : hasTranslation &&
              !translation.showOriginal
            ? 'Show original message'
            : hasTranslation
              ? 'Show English translation'
              : 'Translate to English'}
      </button>

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
  /*
   * A message linked to an offer is NOT automatically an eBay notification.
   * Real buyer/seller chat messages can legitimately be linked to an offer,
   * so message_id matching must never hide them.
   *
   * Only hide rows that are actually system/eBay notification messages.
   */
  const senderType = String(
    message?.sender_type || '',
  ).toUpperCase()

  const senderIdentifier = String(
    message?.sender_identifier || '',
  )
    .trim()
    .toLowerCase()

  const isSystemLike =
    senderType === 'SYSTEM' ||
    senderIdentifier === 'ebay' ||
    isEbayNotificationMessage(message)

  if (!isSystemLike) {
    return false
  }

  if (message?.is_offer_notification) {
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
      'counteroffer submitted to buyer',
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
            originalText:
              message.body,
            showOriginal: false,
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

  const toggleOriginalMessage =
    useCallback((messageId) => {
      setTranslations((current) => {
        const translation =
          current[messageId]

        if (!translation?.text) {
          return current
        }

        return {
          ...current,

          [messageId]: {
            ...translation,
            showOriginal:
              !translation.showOriginal,
          },
        }
      })
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
   * Normalize and deduplicate every structured offer through one helper.
   * Keep FROM_EBAY system conversations message-only, as before.
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

      return collectStructuredOffers(
        messages,
        offers,
        conversation,
      )
    }, [
      messages,
      offers,
      conversation,
      isSystemConversation,
    ])

  /*
   * Offer cards must be placed by the true eBay offer timestamp.
   * Raw eBay offer-notification messages are hidden separately, so linked
   * offers can safely participate in the same sorted timeline as messages.
   */
  const timelineItems =
    useMemo(
      () =>
        buildTimelineItems(
          messages,
          structuredOffers,
        ),
      [messages, structuredOffers],
    )

  const visibleMessageBodies =
    useMemo(
      () =>
        timelineItems
          .filter(
            (item) =>
              item.type === 'message',
          )
          .map(({ message }) =>
            message.body ||
            message.message ||
            message.text ||
            '',
          )
          .filter(Boolean),
      [timelineItems],
    )

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
                  item.originalIndex
                }`}
              >
                <OfferEvent
                  offer={offer}
                  conversation={
                    conversation
                  }
                  visibleMessageBodies={
                    visibleMessageBodies
                  }
                />
              </div>
            )
          }

          const message =
            item.message

          const index =
            item.originalIndex

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
           * Only true eBay/system offer notifications are hidden.
           * Buyer and seller chat messages must remain visible even when the
           * backend linked them to an offer or marked offer metadata on them.
           */
          if (
            isOfferNotificationMessage(
              message,
              structuredOffers,
            )
          ) {
            return null
          }

          const messageBody =
            message.body ||
            message.message ||
            message.text ||
            ''

          const translation =
            translations[message.id]

          const displayMessageBody =
            translation?.text &&
            !translation.showOriginal
              ? translation.text
              : messageBody

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
                <p>{displayMessageBody}</p>
              )}

              {direction ===
                'inbound' &&
              message.body ? (
                <MessageTranslation
                  message={message}
                  translation={
                    translation
                  }
                  isTranslating={
                    translatingId ===
                    message.id
                  }
                  onTranslate={
                    translateBuyerMessage
                  }
                  onToggleOriginal={
                    toggleOriginalMessage
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

import {
  useEffect,
  useState,
} from 'react'

import { Icon } from '../../../layouts/app_layout'

function normalizeImageUrl(imageUrl) {
  if (typeof imageUrl !== 'string') {
    return ''
  }

  return imageUrl
    .trim()
    .replace(
      /^http:\/\//i,
      'https://',
    )
    .replace(/&amp;/g, '&')
}

function ContextThumbnail({
  imageUrl,
  title,
}) {
  const [failed, setFailed] =
    useState(false)

  const normalizedUrl =
    normalizeImageUrl(imageUrl)

  useEffect(() => {
    setFailed(false)
  }, [normalizedUrl])

  if (!normalizedUrl || failed) {
    return <Icon name="package" />
  }

  return (
    <img
      src={normalizedUrl}
      alt={
        title
          ? `${title} preview`
          : 'Item preview'
      }
      loading="eager"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  )
}

function formatContextPrice(
  price,
  currency,
) {
  if (price == null || price === '') {
    return null
  }

  const numericPrice = Number(price)

  if (!Number.isFinite(numericPrice)) {
    return currency
      ? `${price} ${currency}`
      : String(price)
  }

  if (!currency) {
    return new Intl.NumberFormat().format(
      numericPrice,
    )
  }

  try {
    return new Intl.NumberFormat(
      undefined,
      {
        style: 'currency',
        currency,
      },
    ).format(numericPrice)
  } catch {
    return `${numericPrice} ${currency}`
  }
}

function ContextItemBanner({
  context,
  actionLabel,
  actionUrl,
  ariaLabel,
}) {
  if (!context) {
    return null
  }

  const formattedPrice =
    formatContextPrice(
      context.price,
      context.currency,
    )

  const hasIdentifiers = Boolean(
    context.order_id ||
    context.item_id ||
    context.sku,
  )

  return (
    <section
      className="product-context-banner"
      aria-label={ariaLabel}
    >
      <div className="product-context-main">
        <div className="product-context-thumb">
          <ContextThumbnail
            imageUrl={context.image_url}
            title={context.title}
          />
        </div>

        <div className="product-context-body">
          {context.item_url ? (
            <a
              href={context.item_url}
              target="_blank"
              rel="noreferrer"
            >
              <strong>
                {context.title ||
                  'Unknown Item'}
              </strong>
            </a>
          ) : (
            <strong>
              {context.title ||
                'Unknown Item'}
            </strong>
          )}

          {formattedPrice ? (
            <span className="product-context-price">
              {formattedPrice}
            </span>
          ) : null}

          {hasIdentifiers ? (
            <div className="product-context-identifiers">
              {context.order_id ? (
                <span>
                  Order Number:{' '}
                  {context.order_id}
                </span>
              ) : null}

              {context.item_id ? (
                <span>
                  Item ID:{' '}
                  {context.item_id}
                </span>
              ) : null}

              {context.sku ? (
                <span>
                  SKU: {context.sku}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="product-context-actions">
        {context.item_url ? (
          <a
            className="secondary-button compact-action"
            href={context.item_url}
            target="_blank"
            rel="noreferrer"
          >
            Open Item
          </a>
        ) : null}

        {actionLabel &&
        (actionUrl || context.item_url) ? (
          <a
            className="primary-button compact-action"
            href={actionUrl || context.item_url}
            target="_blank"
            rel="noreferrer"
          >
            {actionLabel}
          </a>
        ) : null}
      </div>
    </section>
  )
}

function OrderBanner({ order }) {
  if (!order) {
    return null
  }

  const item =
    order.line_items?.[0] || {}

  const listingId =
    item.item_id ||
    item.listing_id

  const context = {
    title:
      item.title ||
      `Order ${order.order_id}`,
    image_url: item.image_url,
    item_url: listingId
      ? `https://www.ebay.com/itm/${listingId}`
      : '',
    price: item.price_value,
    currency: item.price_currency,
    order_id: order.order_id,
    item_id:
      item.item_id ||
      item.listing_id,
    sku: item.sku,
  }

  return (
    <ContextItemBanner
      context={context}
      actionLabel="Open Order"
      actionUrl={order.ebay_url}
      ariaLabel="Order context"
    />
  )
}

function ProductBanner({ context }) {
  if (!context) {
    return null
  }

  return (
    <ContextItemBanner
      context={{
        ...context,
        item_id: context.reference_id,
      }}
      actionLabel={
        context.buy_now_available
          ? 'Buy It Now'
          : null
      }
      ariaLabel="Product context"
    />
  )
}

function ConversationContextBanner({
  detail,
}) {
  const order =
    detail?.order_context
      ?.selected_order

  if (order) {
    return (
      <OrderBanner order={order} />
    )
  }

  const context =
    detail?.product_context

  if (!context) {
    return null
  }

  return (
    <ProductBanner context={context} />
  )
}

export {
  ContextItemBanner,
  ContextThumbnail,
  OrderBanner,
  ProductBanner,
}

export default ConversationContextBanner

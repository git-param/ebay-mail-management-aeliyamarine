import { ebayMarketplaceHost, ebayListingUrl, localizeEbayUrl } from '../../../utils/ebayUrls'

export function metadataText(value) {
  const text = String(value ?? '').trim()
  return /^(?:-|n\/a)$/i.test(text) ? '' : text
}

function formatPrice(value, currency) {
  const price = metadataText(value)
  if (!price) return ''
  const amount = Number(price)
  if (!Number.isFinite(amount)) return currency ? `${price} ${currency}` : price
  try {
    return new Intl.NumberFormat(undefined, currency
      ? { style: 'currency', currency }
      : {}).format(amount)
  } catch {
    return `${price} ${currency}`
  }
}

export function conversationProductContext(detail) {
  const host = ebayMarketplaceHost(detail.seller_account || {})
  const order = detail.order_context?.selected_order
  const product = detail.product_context
  const item = order?.line_items?.[0] || {}
  const isListing = metadataText(detail.reference_type).toUpperCase() === 'LISTING'
  const itemId = order
    ? metadataText(item.item_id) || metadataText(item.listing_id)
    : metadataText(product?.reference_id)
  const itemNumber = itemId || (isListing ? metadataText(detail.reference_id) : '')
  const itemUrl = order
    ? ebayListingUrl(itemNumber, host)
    : localizeEbayUrl(metadataText(product?.item_url) || ebayListingUrl(itemNumber, host), host)

  return {
    title: metadataText(order ? item.title : product?.title),
    imageUrl: metadataText(order ? item.image_url : product?.image_url),
    price: formatPrice(order ? item.price_value : product?.price,
      metadataText(order ? item.price_currency : product?.currency)),
    itemNumber,
    itemUrl,
    orderNumber: metadataText(order?.order_id),
    orderUrl: localizeEbayUrl(metadataText(order?.ebay_url), host),
    sku: metadataText(order ? item.sku : product?.sku),
    reference: isListing ? '' : metadataText(detail.reference_id),
    referenceType: isListing ? '' : metadataText(detail.reference_type),
  }
}

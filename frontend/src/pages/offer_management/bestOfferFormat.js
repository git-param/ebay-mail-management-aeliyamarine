export function bestOfferMoney(amount, currency) {
  if (amount == null || amount === '' || !currency || !Number.isFinite(Number(amount))) return '—'
  currency = String(currency).trim().toUpperCase()
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(amount)) }
  catch { return `${amount} ${currency}` }
}

export function bestOfferStatusKey(value) {
  return String(value || '').trim().toUpperCase()
}

export function bestOfferStatusLabel(value) {
  const labels = { ADMINENDED: 'Ended by eBay', SELLERACCEPT: 'Seller accepted', PENDINGBUYERPAYMENT: 'Awaiting buyer payment', PENDINGBUYERCONFIRMATION: 'Awaiting buyer confirmation' }
  if (labels[bestOfferStatusKey(value)]) return labels[bestOfferStatusKey(value)]
  const words = String(value || '').trim().replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ')
  return words ? words.toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase()) : 'Unknown'
}

export function bestOfferStatusGroup(value) {
  const key = bestOfferStatusKey(value)
  if (['ACTIVE', 'PENDING', 'COUNTERED'].includes(key)) return 'OPEN'
  if (['SELLERACCEPT', 'PENDINGBUYERCONFIRMATION', 'PENDINGBUYERPAYMENT'].includes(key)) return 'AGREED'
  if (key === 'ACCEPTED') return 'COMPLETED'
  if (['DECLINED', 'EXPIRED', 'RETRACTED', 'WITHDRAWN', 'ADMINENDED'].includes(key)) return 'CLOSED'
  return 'UNKNOWN'
}

export const bestOfferGroupLabels = { OPEN: 'Open', AGREED: 'Waiting for buyer', COMPLETED: 'Completed', CLOSED: 'Closed', UNKNOWN: 'Other statuses' }

export function bestOfferPrices(offer) {
  const currency = String(offer.currency || '').trim().toUpperCase()
  const listingCurrency = String(offer.listing?.currency || '').trim().toUpperCase()
  const hasListingPrice = offer.listing?.price != null && offer.listing.price !== ''
  const matches = Boolean(currency && listingCurrency && currency === listingCurrency)
  return {
    currency,
    amount: bestOfferMoney(offer.amount, currency),
    listingPrice: matches ? bestOfferMoney(offer.listing?.price, currency) : '—',
    listingNote: hasListingPrice && !matches
      ? (currency && listingCurrency ? `Listing price unavailable in ${currency}` : 'Listing currency unconfirmed')
      : '',
  }
}

export function bestOfferDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}


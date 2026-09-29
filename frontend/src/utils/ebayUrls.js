export function ebayMarketplaceHost(account = {}) {
  const text = [account.account_name, account.ebay_username, account.name].filter(Boolean).join(' ').toLowerCase()
  if (text.includes('marine') || text.includes('marin')) return 'www.ebay.co.uk'
  if (text.includes('trade')) return 'www.ebay.de'
  return 'www.ebay.com'
}

export function ebayListingUrl(itemId, host = 'www.ebay.com') {
  const id = String(itemId ?? '').trim()
  return id ? `https://${host}/itm/${encodeURIComponent(id)}` : ''
}

export function localizeEbayUrl(value, host) {
  if (!value) return ''
  try {
    const url = new URL(value)
    if (/(^|\.)ebay\.(com|co\.uk|de)$/i.test(url.hostname)) {
      url.hostname = host
      url.protocol = 'https:'
    }
    return url.toString()
  } catch { return String(value) }
}

export function normalizeProductImageUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  const normalized = value.trim().replace(/&amp;/g, '&').replace(/^http:\/\//i, 'https://').replace(/^\/\//, 'https://')
  try {
    const url = new URL(normalized)
    return url.protocol === 'https:' ? url.toString() : ''
  } catch { return '' }
}

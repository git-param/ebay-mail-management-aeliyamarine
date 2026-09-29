import assert from 'node:assert/strict'
import test from 'node:test'
import { ebayMarketplaceHost, ebayListingUrl, localizeEbayUrl, normalizeProductImageUrl } from './ebayUrls.js'

test('listing and order links follow the managed account, regardless of the other party', () => {
  for (const [account, host] of [
    [{ account_name: 'Marine' }, 'www.ebay.co.uk'],
    [{ account_name: 'Warehouse', ebay_username: 'aeliya-marin110' }, 'www.ebay.co.uk'],
    [{ account_name: 'TRADE' }, 'www.ebay.de'],
    [{ account_name: 'Tools' }, 'www.ebay.com'],
  ]) {
    assert.equal(ebayMarketplaceHost(account), host)
    assert.equal(ebayListingUrl('123456', host), `https://${host}/itm/123456`)
    assert.equal(localizeEbayUrl('https://www.ebay.com/sh/ord/details?orderid=12-34#details', host), `https://${host}/sh/ord/details?orderid=12-34#details`)
  }
  assert.equal(ebayListingUrl(null), '')
})

test('bare regional eBay domains localize while other domains stay intact', () => {
  assert.equal(localizeEbayUrl('http://ebay.de/itm/123', 'www.ebay.co.uk'), 'https://www.ebay.co.uk/itm/123')
  assert.equal(localizeEbayUrl('https://example.com/order/123', 'www.ebay.de'), 'https://example.com/order/123')
})

test('image previews normalize insecure, protocol-relative and escaped URLs', () => {
  assert.equal(normalizeProductImageUrl(' http://i.ebayimg.com/image.jpg?a=1&amp;b=2 '), 'https://i.ebayimg.com/image.jpg?a=1&b=2')
  assert.equal(normalizeProductImageUrl('//i.ebayimg.com/image.jpg'), 'https://i.ebayimg.com/image.jpg')
  for (const value of [null, '', 'invalid', 'javascript:alert(1)']) assert.equal(normalizeProductImageUrl(value), '')
})

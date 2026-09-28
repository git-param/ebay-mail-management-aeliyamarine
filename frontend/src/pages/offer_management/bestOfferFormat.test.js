import assert from 'node:assert/strict'
import test from 'node:test'
import { bestOfferMoney, bestOfferPrices, bestOfferStatusKey, bestOfferStatusLabel, bestOfferStatusGroup } from './bestOfferFormat.js'

test('a EUR offer never displays an unrelated cached USD listing amount', () => {
  const prices = bestOfferPrices({ amount: '900.59', currency: 'EUR', listing: { price: '1086.87', currency: 'USD' } })
  assert.equal(prices.currency, 'EUR')
  assert.match(prices.amount, /900[.,]59/)
  assert.equal(prices.listingPrice, '—')
  assert.equal(prices.listingNote, 'Listing price unavailable in EUR')
})

test('matching currencies keep both prices, including zero, with normalized codes', () => {
  const prices = bestOfferPrices({ amount: '20', currency: ' usd ', listing: { price: 0, currency: 'USD' } })
  assert.equal(prices.currency, 'USD')
  assert.equal(prices.amount, bestOfferMoney(20, 'USD'))
  assert.equal(prices.listingPrice, bestOfferMoney(0, 'USD'))
  assert.equal(prices.listingNote, '')
})

test('unconfirmed currencies and invalid amounts cannot produce misleading prices', () => {
  assert.equal(bestOfferPrices({ currency: 'EUR', listing: { price: 30 } }).listingPrice, '—')
  assert.equal(bestOfferPrices({ listing: { price: 30, currency: 'USD' } }).amount, '—')
  for (const value of [null, '', 'invalid', Infinity]) assert.equal(bestOfferMoney(value, 'USD'), '—')
})

test('legacy capitalization shares a filter key and readable label', () => {
  const keys = new Set(['Accepted', 'ACCEPTED', ' accepted ', 'Pending', 'PENDING'].map(bestOfferStatusKey))
  assert.deepEqual([...keys], ['ACCEPTED', 'PENDING'])
  assert.equal(bestOfferStatusLabel('ACCEPTED'), 'Accepted')
  assert.equal(bestOfferStatusLabel('PENDINGBUYERPAYMENT'), 'Awaiting buyer payment')
})

test('agreements stay distinct from completed offers and unknown provider states', () => {
  for (const state of ['SellerAccept', 'PendingBuyerConfirmation', 'PendingBuyerPayment']) {
    assert.equal(bestOfferStatusGroup(state), 'AGREED')
  }
  assert.equal(bestOfferStatusGroup('Accepted'), 'COMPLETED')
  assert.equal(bestOfferStatusGroup('AdminEnded'), 'CLOSED')
  assert.equal(bestOfferStatusLabel('AdminEnded'), 'Ended by eBay')
  assert.equal(bestOfferStatusGroup('FutureProviderState'), 'UNKNOWN')
})

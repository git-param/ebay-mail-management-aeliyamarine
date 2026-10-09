import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clearOrderRecipientParams,
  getOrderRecipientFromUrl,
  orderConversationUrl,
} from './orderConversationNavigation.js'

test('existing order conversation opens the selected thread', () => {
  assert.equal(orderConversationUrl({ conversation_id: 'thread-123' }), '/inbox?conversation_id=thread-123')
})

test('new order conversation carries the correct recipient and account through navigation', () => {
  const result = {
    conversation_id: null, buyer_username: 'buyer+name', account_id: 'seller-account',
    order_id: '12-34/56', account_name: 'Tech & Main',
  }
  const url = new URL(orderConversationUrl(result), 'http://localhost')
  globalThis.window = { location: { search: url.search } }
  try {
    assert.deepEqual(getOrderRecipientFromUrl(), {
      buyerUsername: result.buyer_username, accountId: result.account_id,
      orderId: result.order_id, accountName: result.account_name,
    })
    clearOrderRecipientParams(url)
    assert.equal(url.search, '')
    window.location.search = '?new_buyer=buyer'
    assert.equal(getOrderRecipientFromUrl(), null)
  } finally {
    delete globalThis.window
  }
})

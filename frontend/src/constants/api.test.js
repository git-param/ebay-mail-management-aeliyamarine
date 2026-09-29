import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'
import { parse } from '@babel/parser'
import { API, API_PREFIX, apiPath, getApiBaseUrl } from './api.js'

test('API templates preserve prepared identifiers and reject missing parameters', () => {
  assert.equal(apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID_NOTES_BY_NOTE_ID, {
    conversationId: 'thread-1', noteId: 'note-2',
  }), '/conversations/thread-1/notes/note-2')
  assert.equal(apiPath(API.SOLD_POSTING.ORDERS_BY_ORDER_ID, {
    orderId: encodeURIComponent('12/34 ?'),
  }), '/sold-posting/orders/12%2F34%20%3F')
  assert.throws(() => apiPath(API.CONVERSATIONS.BY_CONVERSATION_ID), /Missing API path parameter/)
  assert.equal(getApiBaseUrl(), API_PREFIX)
})

test('frontend services import endpoint constants instead of defining API paths', () => {
  const serviceDir = new URL('../services/', import.meta.url)
  const errors = []
  function visit(node, file) {
    if (!node || typeof node !== 'object') return
    if (node.type === 'StringLiteral' && node.value.startsWith('/') && node.value.length > 1) {
      errors.push(`${file}:${node.loc.start.line}`)
    }
    if (node.type === 'TemplateElement' && /\/(auth|api|integrations|conversations|categories|users|offers|reports|pms|templates|notifications|audit-logs|analytics|config|search-sku|sold-posting|dailyEntry|task-management|leave-management|offer-management|break-management|message-types|ebay-accounts)(\/|\?|$)/.test(node.value.cooked)) {
      errors.push(`${file}:${node.loc.start.line}`)
    }
    for (const [key, value] of Object.entries(node)) {
      if (['loc', 'comments', 'tokens'].includes(key)) continue
      if (Array.isArray(value)) value.forEach((item) => visit(item, file))
      else if (value && typeof value === 'object') visit(value, file)
    }
  }
  for (const file of readdirSync(serviceDir).filter((name) => name.endsWith('.js'))) {
    const ast = parse(readFileSync(new URL(file, serviceDir), 'utf8'), { sourceType: 'module' })
    visit(ast, file)
  }
  assert.deepEqual(errors, [], 'Move API paths into src/constants/api.js')
})

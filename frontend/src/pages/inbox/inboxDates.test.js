import assert from 'node:assert/strict'
import test from 'node:test'
import { inboxRequestFilters, periodRange } from './inboxDates.js'

process.env.TZ = 'Asia/Kolkata'

test('custom range includes the complete final local day exactly once', () => {
  const result = inboxRequestFilters({ period: 'custom', date_from: '2026-01-02', date_to: '2026-02-02', status: 'OPEN' })
  assert.equal(result.date_from, '2026-01-01T18:30:00.000Z')
  assert.equal(result.date_to, '2026-02-02T18:30:00.000Z')
  assert.equal(result.status, 'OPEN')
  assert.equal(result.period, undefined)
})

test('single day, open ranges, leap day and year rollover', () => {
  for (const [day, next] of [['2026-01-02', '2026-01-02'], ['2024-02-29', '2024-02-29'], ['2026-12-31', '2026-12-31']]) {
    const result = inboxRequestFilters({ period: 'custom', date_from: day, date_to: day })
    assert.equal(new Date(result.date_to) - new Date(result.date_from), 86400000)
    assert.ok(result.date_to.startsWith(next))
  }
  assert.equal(inboxRequestFilters({ period: 'custom', date_from: '', date_to: '2026-02-02' }).date_from, '')
  assert.equal(inboxRequestFilters({ period: 'custom', date_from: '2026-02-02', date_to: '' }).date_to, '')
  assert.throws(() => inboxRequestFilters({ period: 'custom', date_from: '2026-02-02', date_to: '2026-01-02' }), /From date/)
})

test('preset UI dates are inclusive and requests expand the end only once', () => {
  const now = new Date(2026, 9, 2, 12)
  assert.deepEqual(periodRange('today', now), { date_from: '2026-10-02', date_to: '2026-10-02' })
  assert.deepEqual(periodRange('yesterday', now), { date_from: '2026-10-01', date_to: '2026-10-01' })
  assert.deepEqual(periodRange('30', now), { date_from: '2026-09-03', date_to: '2026-10-02' })
  assert.deepEqual(periodRange('month', now), { date_from: '2026-10-01', date_to: '2026-10-02' })
  assert.deepEqual(periodRange('year', now), { date_from: '2026-01-01', date_to: '2026-10-02' })
  assert.deepEqual(inboxRequestFilters({ period: 'all', date_from: '2026-01-01', date_to: '2026-01-02' }), { date_from: '', date_to: '' })
  const customFromPreset = inboxRequestFilters({ period: 'custom', ...periodRange('today', now) })
  assert.equal(customFromPreset.date_to, '2026-10-02T18:30:00.000Z')
  const request = inboxRequestFilters({ period: 'yesterday' })
  assert.equal(new Date(request.date_to) - new Date(request.date_from), 86400000)
})

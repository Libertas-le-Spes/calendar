const test = require('node:test')
const assert = require('node:assert/strict')
const { loadQmlJs } = require('./load-qml-js')

const EventsFile = loadQmlJs('EventsFile.js')

function document(events) {
  return JSON.stringify({ version: 1, syncedAt: '2026-10-21T08:00:00Z', source: 'made-up/1', events })
}

function rows(count) {
  return Array.from({ length: count }, (_, index) => ({ id: `made-up-${index}` }))
}

test('a sound document is read with its events', () => {
  const result = EventsFile.read(document(rows(2)))
  assert.equal(result.problem, '')
  assert.equal(EventsFile.eventsOf(result).length, 2)
})

test('no file at all is missing', () => {
  assert.equal(EventsFile.read('').problem, 'missing')
})

test('text that is not JSON is missing', () => {
  assert.equal(EventsFile.read('{not json').problem, 'missing')
})

test('JSON that is not an object is missing', () => {
  assert.equal(EventsFile.read('[1, 2]').problem, 'missing')
})

test('a document with no version is missing', () => {
  assert.equal(EventsFile.read(JSON.stringify({ events: [] })).problem, 'missing')
})

test('a document from a newer version says so', () => {
  assert.equal(EventsFile.read(JSON.stringify({ version: 2, events: [] })).problem, 'version')
})

test('a document whose events are not a list is missing', () => {
  assert.equal(EventsFile.read(JSON.stringify({ version: 1, events: {} })).problem, 'missing')
})

test('a document at the row ceiling is read', () => {
  assert.equal(EventsFile.read(document(rows(EventsFile.MAX_EVENT_ROWS))).problem, '')
})

test('a document one row over the ceiling is refused as too large', () => {
  const result = EventsFile.read(document(rows(EventsFile.MAX_EVENT_ROWS + 1)))
  assert.equal(result.problem, 'too-large')
  assert.deepEqual(EventsFile.eventsOf(result), [])
})

test('text longer than the size ceiling is refused before it is parsed', () => {
  const original = JSON.parse
  let parses = 0
  JSON.parse = (...args) => { parses += 1; return original(...args) }
  try {
    const result = EventsFile.read(' '.repeat(EventsFile.MAX_DOCUMENT_BYTES + 1))
    assert.equal(result.problem, 'too-large')
  } finally {
    JSON.parse = original
  }
  assert.equal(parses, 0)
})

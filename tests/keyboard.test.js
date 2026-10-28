const test = require('node:test')
const assert = require('node:assert/strict')
const { loadQmlJs } = require('./load-qml-js')

const Keyboard = loadQmlJs('Keyboard.js')

test('Tab walks the controls forward', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_TAB, 0, false), 'walk')
  assert.equal(Keyboard.tabStep(Keyboard.KEY_TAB, 0), 1)
})

test('Shift+Tab walks the controls back', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_BACKTAB, Keyboard.SHIFT, false), 'walk')
  assert.equal(Keyboard.tabStep(Keyboard.KEY_BACKTAB, Keyboard.SHIFT), -1)
  assert.equal(Keyboard.tabStep(Keyboard.KEY_TAB, Keyboard.SHIFT), -1)
})

test('Ctrl+Tab switches to the next bar panel', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_TAB, Keyboard.CONTROL, false), 'switch')
})

test('Ctrl+Tab stays put while the event form is open, so a half-written event is kept', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_TAB, Keyboard.CONTROL, true), 'stay')
})

test('Tab still walks while the event form is open', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_TAB, 0, true), 'walk')
})

test('a key that is not Tab is left alone', () => {
  assert.equal(Keyboard.tabAction(Keyboard.KEY_LEFT, 0, false), 'none')
})

test('left and up step back, right and down step forward, anything else not at all', () => {
  assert.equal(Keyboard.arrowStep(Keyboard.KEY_LEFT), -1)
  assert.equal(Keyboard.arrowStep(Keyboard.KEY_UP), -1)
  assert.equal(Keyboard.arrowStep(Keyboard.KEY_RIGHT), 1)
  assert.equal(Keyboard.arrowStep(Keyboard.KEY_DOWN), 1)
  assert.equal(Keyboard.arrowStep(Keyboard.KEY_TAB), 0)
})

test('j and k step through the day, and not with Ctrl held', () => {
  assert.equal(Keyboard.itemStep('j', 0), 1)
  assert.equal(Keyboard.itemStep('k', 0), -1)
  assert.equal(Keyboard.itemStep('j', Keyboard.CONTROL), 0)
  assert.equal(Keyboard.itemStep('x', 0), 0)
})

test('a control already in view does not scroll', () => {
  assert.equal(Keyboard.scrollToShow(100, 300, 1000, 200, 20, 8), 100)
})

test('a control above the view scrolls up to it, with a margin', () => {
  assert.equal(Keyboard.scrollToShow(100, 300, 1000, 50, 20, 8), 42)
})

test('a control below the view scrolls down until it shows, with a margin', () => {
  assert.equal(Keyboard.scrollToShow(100, 300, 1000, 500, 20, 8), 228)
})

test('scrolling never passes the top or the end of the content', () => {
  assert.equal(Keyboard.scrollToShow(100, 300, 1000, 2, 20, 8), 0)
  assert.equal(Keyboard.scrollToShow(100, 300, 1000, 990, 20, 8), 700)
})

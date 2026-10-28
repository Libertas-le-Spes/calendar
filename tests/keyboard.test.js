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

const QUIET = { dialogOpen: false, formOpen: false, inText: false, onButton: false }

function stateWith(changes) {
  return Object.assign({}, QUIET, changes)
}

test('the key numbers are the ones Qt sends', () => {
  assert.equal(Keyboard.KEY_TAB, 16777217)
  assert.equal(Keyboard.KEY_BACKTAB, 16777218)
  assert.equal(Keyboard.KEY_RETURN, 16777220)
  assert.equal(Keyboard.KEY_LEFT, 16777234)
  assert.equal(Keyboard.KEY_UP, 16777235)
  assert.equal(Keyboard.KEY_RIGHT, 16777236)
  assert.equal(Keyboard.KEY_DOWN, 16777237)
  assert.equal(Keyboard.KEY_SPACE, 32)
  assert.equal(Keyboard.SHIFT, 33554432)
  assert.equal(Keyboard.CONTROL, 67108864)
})

test('while the delete confirmation is open every key goes to it', () => {
  for (const [key, text] of [[Keyboard.KEY_TAB, ''], [0x4e, 'n'], [Keyboard.KEY_SPACE, ' '], [Keyboard.KEY_DOWN, '']]) {
    assert.equal(Keyboard.keyAction(key, 0, text, stateWith({ dialogOpen: true })).action, 'dialog')
  }
})

test('Tab walks even from inside a text field', () => {
  assert.deepEqual(Keyboard.keyAction(Keyboard.KEY_TAB, 0, '', stateWith({ inText: true })), { action: 'walk', step: 1 })
})

test('a text field keeps every other key', () => {
  assert.equal(Keyboard.keyAction(Keyboard.KEY_LEFT, 0, '', stateWith({ inText: true, onButton: true })).action, 'none')
  assert.equal(Keyboard.keyAction(0x4a, 0, 'j', stateWith({ inText: true })).action, 'none')
})

test('j and k step through the day when no form is open', () => {
  assert.deepEqual(Keyboard.keyAction(0x4a, 0, 'j', QUIET), { action: 'step-item', step: 1 })
  assert.equal(Keyboard.keyAction(0x4a, 0, 'j', stateWith({ formOpen: true })).action, 'none')
})

test('the arrows walk from a button and are left to the panel otherwise', () => {
  assert.deepEqual(Keyboard.keyAction(Keyboard.KEY_RIGHT, 0, '', stateWith({ onButton: true })), { action: 'walk', step: 1 })
  assert.equal(Keyboard.keyAction(Keyboard.KEY_RIGHT, 0, '', QUIET).action, 'none')
})

test('Ctrl+Tab switches panels, and stays put while the form is open', () => {
  assert.equal(Keyboard.keyAction(Keyboard.KEY_TAB, Keyboard.CONTROL, '', QUIET).action, 'switch')
  assert.equal(Keyboard.keyAction(Keyboard.KEY_TAB, Keyboard.CONTROL, '', stateWith({ formOpen: true })).action, 'stay')
})

test('Space in the delete confirmation answers like Enter', () => {
  assert.deepEqual(Keyboard.dialogKey(Keyboard.KEY_SPACE), { key: Keyboard.KEY_RETURN })
  assert.deepEqual(Keyboard.dialogKey(Keyboard.KEY_LEFT), { key: Keyboard.KEY_LEFT })
})

.pragma library

var KEY_TAB = 0x01000001
var KEY_BACKTAB = 0x01000002
var KEY_LEFT = 0x01000012
var KEY_UP = 0x01000013
var KEY_RIGHT = 0x01000014
var KEY_DOWN = 0x01000015
var SHIFT = 0x02000000
var CONTROL = 0x04000000

var ARROW_STEPS = {}
ARROW_STEPS[KEY_LEFT] = -1
ARROW_STEPS[KEY_UP] = -1
ARROW_STEPS[KEY_RIGHT] = 1
ARROW_STEPS[KEY_DOWN] = 1

function isTab(key) {
  return key === KEY_TAB || key === KEY_BACKTAB
}

function tabStep(key, modifiers) {
  if (key === KEY_BACKTAB || (modifiers & SHIFT)) return -1
  return 1
}

function tabAction(key, modifiers, formOpen) {
  if (!isTab(key)) return "none"
  if (!(modifiers & CONTROL)) return "walk"
  if (formOpen) return "stay"
  return "switch"
}

function arrowStep(key) {
  var step = ARROW_STEPS[key]
  if (step === undefined) return 0
  return step
}

function itemStep(text, modifiers) {
  if (modifiers & CONTROL) return 0
  if (text === "j") return 1
  if (text === "k") return -1
  return 0
}

function scrollToShow(contentY, viewHeight, contentHeight, itemTop, itemHeight, margin) {
  var wanted = contentY
  if (itemTop - margin < contentY) wanted = itemTop - margin
  if (itemTop + itemHeight + margin > contentY + viewHeight) wanted = itemTop + itemHeight + margin - viewHeight
  var furthest = Math.max(0, contentHeight - viewHeight)
  return Math.max(0, Math.min(wanted, furthest))
}

var KEY_SPACE = 0x20
var KEY_RETURN = 0x01000004
var KEY_ENTER = 0x01000005
var CONFIRM_CANCEL = 0

var CONFIRM_TOGGLES = {}
CONFIRM_TOGGLES[KEY_LEFT] = true
CONFIRM_TOGGLES[KEY_RIGHT] = true
CONFIRM_TOGGLES[KEY_TAB] = true
CONFIRM_TOGGLES[KEY_BACKTAB] = true

var CONFIRM_ANSWERS = {}
CONFIRM_ANSWERS[KEY_RETURN] = true
CONFIRM_ANSWERS[KEY_ENTER] = true
CONFIRM_ANSWERS[KEY_SPACE] = true

function keyAction(key, modifiers, text, state) {
  if (state.dialogOpen) return { action: "dialog", step: 0 }
  var tab = tabAction(key, modifiers, state.formOpen)
  if (tab !== "none") return { action: tab, step: tabStep(key, modifiers) }
  if (state.inText) return { action: "none", step: 0 }
  var item = itemStep(text, modifiers)
  if (item !== 0 && !state.formOpen) return { action: "step-item", step: item }
  var arrow = arrowStep(key)
  if (arrow !== 0 && state.onButton) return { action: "walk", step: arrow }
  return { action: "none", step: 0 }
}

function confirmKey(key, choice) {
  if (CONFIRM_TOGGLES[key]) return { choice: 1 - choice, key: 0 }
  if (CONFIRM_ANSWERS[key]) return { choice: choice, key: KEY_RETURN }
  return { choice: choice, key: key }
}

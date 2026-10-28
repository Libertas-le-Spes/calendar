import QtQuick
import qs.Commons
import "Keyboard.js" as Keyboard

Item {
  id: walker

  property bool opened: false
  property bool formOpen: false
  property Item formArea: null
  property Item confirmDialog: null
  property var takesText: null
  property bool walking: false

  readonly property Item keyTarget: keyFocus
  readonly property Item focused: Window.activeFocusItem
  readonly property bool focusedShown: focused !== null && focused.visible

  signal switchPanelRequested(int step)
  signal itemStepRequested(int step)

  readonly property var actions: ({
    "dialog": walker.answerDialog,
    "walk": walker.walkFrom,
    "switch": walker.switchPanel,
    "stay": walker.stay,
    "step-item": walker.stepItem
  })

  Keys.onPressed: function(event) { walker.handle(event) }
  onFocusedChanged: walker.settle(focused)
  onFocusedShownChanged: if (!focusedShown) walker.recover()

  Item {
    id: keyFocus
    focus: true
  }

  function handle(event) {
    var decision = Keyboard.keyAction(event.key, event.modifiers, event.text, walker.state())
    var act = walker.actions[decision.action]
    if (!act) return
    act(decision.step, event)
    event.accepted = true
  }

  function state() {
    return {
      dialogOpen: walker.confirmDialog !== null && walker.confirmDialog.opened === true,
      formOpen: walker.formOpen,
      inText: walker.takesText(walker.focused),
      onButton: walker.focused !== null && walker.focused !== keyFocus && walker.focused.ownsArrows !== true
    }
  }

  function answerDialog(step, event) {
    walker.confirmDialog.handleKey(Keyboard.dialogKey(event.key))
  }

  function walkFrom(step, event) {
    walker.walk(step)
  }

  function switchPanel(step, event) {
    walker.switchPanelRequested(step)
  }

  function stay(step, event) {
  }

  function stepItem(step, event) {
    walker.itemStepRequested(step)
  }

  function walk(step) {
    var next = walker.nextStop(step)
    if (!next) return
    walker.walking = true
    next.forceActiveFocus(Qt.TabFocusReason)
    walker.walking = false
  }

  function nextStop(step) {
    var start = walker.focused
    if (!start) start = keyFocus
    var fence = walker.fence()
    var candidate = start
    for (var tries = 0; tries < 1000; tries++) {
      candidate = candidate.nextItemInFocusChain(step > 0)
      if (!candidate || candidate === start) return null
      if (!fence || walker.holds(fence, candidate)) return candidate
    }
    return null
  }

  function fence() {
    if (walker.formOpen) return walker.formArea
    return null
  }

  function focusKeys() {
    Qt.callLater(function() { keyFocus.forceActiveFocus() })
  }

  function recover() {
    if (walker.opened) walker.focusKeys()
  }

  function settle(item) {
    if (!walker.opened) return
    if (walker.lost(item)) return walker.focusKeys()
    if (walker.takenByMouse(item)) return walker.focusKeys()
    walker.ensureVisible(item)
  }

  function lost(item) {
    if (item === null || item === walker.Window.contentItem) return true
    return item.sourceComponent !== undefined && item.status !== undefined
  }

  function takenByMouse(item) {
    if (walker.walking || item === keyFocus) return false
    if (walker.takesText(item)) return false
    return walker.holds(walker, item)
  }

  function holds(ancestor, item) {
    var cursor = item
    while (cursor) {
      if (cursor === ancestor) return true
      cursor = cursor.parent
    }
    return false
  }

  function ensureVisible(item) {
    var scroller = walker.scrollerOf(item)
    if (!scroller) return
    var spot = item.mapToItem(scroller.contentItem, 0, 0)
    scroller.contentY = Keyboard.scrollToShow(scroller.contentY, scroller.height, scroller.contentHeight,
      spot.y, item.height, Style.space(8))
  }

  function scrollerOf(item) {
    var cursor = item
    while (cursor) {
      var parentItem = cursor.parent
      if (parentItem && parentItem.parent && parentItem.parent.contentItem === parentItem) return parentItem.parent
      cursor = parentItem
    }
    return null
  }
}

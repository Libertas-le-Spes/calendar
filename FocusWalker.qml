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
  property bool pointerJustUsed: false
  property Item lastFocused: null
  property int confirmChoice: Keyboard.CONFIRM_CANCEL

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

  Connections {
    target: walker.confirmDialog
    function onOpenedChanged() { walker.startConfirm() }
  }

  Item {
    anchors.fill: parent
    z: 1000

    PointHandler {
      acceptedButtons: Qt.AllButtons
      onActiveChanged: walker.notePointer(active)
    }
  }

  function notePointer(pressed) {
    if (pressed) walker.pointerJustUsed = true
    else Qt.callLater(walker.forgetPointer)
  }

  function forgetPointer() {
    walker.pointerJustUsed = false
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

  function startConfirm() {
    if (!walker.confirmDialog.opened) return
    walker.confirmChoice = Keyboard.CONFIRM_CANCEL
    walker.confirmDialog.selectedIndex = walker.confirmChoice
  }

  function answerDialog(step, event) {
    var answer = Keyboard.confirmKey(event.key, walker.confirmChoice)
    walker.confirmChoice = answer.choice
    walker.confirmDialog.selectedIndex = answer.choice
    if (answer.key !== 0) walker.confirmDialog.handleKey({ key: answer.key })
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
    if (next) next.forceActiveFocus(Qt.TabFocusReason)
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
    Qt.callLater(walker.takeKeys)
  }

  function takeKeys() {
    keyFocus.forceActiveFocus()
  }

  function giveBack(from) {
    if (from && from.visible && walker.takesText(from)) return Qt.callLater(walker.focusOn, from)
    walker.focusKeys()
  }

  function focusOn(item) {
    item.forceActiveFocus()
  }

  function recover() {
    if (walker.opened) walker.focusKeys()
  }

  function settle(item) {
    var from = walker.lastFocused
    walker.lastFocused = item
    if (!walker.opened) return
    if (walker.lost(item)) return walker.focusKeys()
    if (walker.takenByMouse(item)) return walker.giveBack(from)
    if (walker.leftTheForm(item)) return Qt.callLater(walker.returnToForm, item, from)
    walker.ensureVisible(item)
  }

  function lost(item) {
    if (item === null || item === walker.Window.contentItem) return true
    return item.sourceComponent !== undefined && item.status !== undefined
  }

  function takenByMouse(item) {
    if (!walker.pointerJustUsed || item === keyFocus) return false
    if (walker.takesText(item)) return false
    return walker.holds(walker, item)
  }

  function leftTheForm(item) {
    var fence = walker.fence()
    if (!fence || item === keyFocus) return false
    return walker.holds(walker, item) && !walker.holds(fence, item)
  }

  function returnToForm(item, from) {
    var fence = walker.fence()
    if (!fence || !item.activeFocus) return
    var lookBack = !walker.followsInTabOrder(from, item, true)
    var lookAhead = !walker.followsInTabOrder(from, item, false)
    var back = item
    var ahead = item
    for (var tries = 0; tries < 1000; tries++) {
      back = back.nextItemInFocusChain(false)
      if (lookBack && walker.holds(fence, back)) return back.forceActiveFocus(Qt.BacktabFocusReason)
      ahead = ahead.nextItemInFocusChain(true)
      if (lookAhead && walker.holds(fence, ahead)) return ahead.forceActiveFocus(Qt.TabFocusReason)
    }
    walker.focusKeys()
  }

  function followsInTabOrder(from, item, forward) {
    if (!from) return false
    return from.nextItemInFocusChain(forward) === item
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

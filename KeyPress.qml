import QtQuick

Item {
  id: root

  signal activated()

  anchors.fill: parent
  activeFocusOnTab: enabled && visible

  Keys.onReturnPressed: function(event) { root.press(event) }
  Keys.onEnterPressed: function(event) { root.press(event) }
  Keys.onSpacePressed: function(event) { root.press(event) }

  function press(event) {
    root.activated()
    event.accepted = true
  }

  FocusRing { target: root }
}

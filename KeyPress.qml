import QtQuick
import qs.Commons

Item {
  id: root

  signal activated()

  property int ringOutset: Style.space(3)

  anchors.fill: parent
  activeFocusOnTab: enabled && visible

  Keys.onReturnPressed: function(event) { root.press(event) }
  Keys.onEnterPressed: function(event) { root.press(event) }
  Keys.onSpacePressed: function(event) { root.press(event) }

  function press(event) {
    root.activated()
    event.accepted = true
  }

  FocusRing {
    target: root
    outset: root.ringOutset
  }
}

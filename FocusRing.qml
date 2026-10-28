import QtQuick
import qs.Commons

Rectangle {
  property Item target: parent
  property bool shown: target.activeFocus

  anchors.fill: target
  anchors.margins: -Style.space(3)
  visible: shown
  color: "transparent"
  radius: Style.cornerRadius + Style.space(3)
  border.width: Style.space(2)
  border.color: Color.accent
  z: 10
}

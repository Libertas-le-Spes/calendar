import QtQuick

Rectangle {
  id: root

  property bool focusable: false
  property string text: ""
  property bool bordered: false
  property string fontFamily: ""

  signal clicked()

  implicitWidth: 40
  implicitHeight: 20
  activeFocusOnTab: focusable
  Keys.onReturnPressed: if (focusable) root.clicked()
  Keys.onEnterPressed: if (focusable) root.clicked()
  Keys.onSpacePressed: if (focusable) root.clicked()

  MouseArea {
    anchors.fill: parent
    onClicked: {
      if (root.focusable) root.forceActiveFocus()
      root.clicked()
    }
  }
}

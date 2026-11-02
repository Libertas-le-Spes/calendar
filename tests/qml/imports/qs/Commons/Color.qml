pragma Singleton
import QtQuick

QtObject {
  property color accent: "orange"
  property color background: "black"
  property var popups: ({ background: "black", border: "gray", text: "white" })
}

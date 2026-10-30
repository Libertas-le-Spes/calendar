pragma Singleton
import QtQuick

QtObject {
  property int cornerRadius: 4
  property int normalBorderWidth: 1
  property var font: ({ family: "sans", bodySmall: 12 })

  function space(size) {
    return size
  }
}

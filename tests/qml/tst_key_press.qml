import QtQuick
import QtTest
import "../.."

Item {
  width: 200
  height: 100

  Item {
    width: 40
    height: 20

    KeyPress { id: press }
  }

  SignalSpy { id: activatedSpy; target: press; signalName: "activated" }

  TestCase {
    name: "KeyPress"
    when: windowShown

    function init() {
      activatedSpy.clear()
      press.enabled = true
      press.forceActiveFocus()
    }

    function test_enter_return_and_space_press_it() {
      keyClick(Qt.Key_Return)
      keyClick(Qt.Key_Enter)
      keyClick(Qt.Key_Space)
      compare(activatedSpy.count, 3)
    }

    function test_a_disabled_one_is_not_a_tab_stop() {
      press.enabled = false
      verify(!press.activeFocusOnTab)
    }
  }
}

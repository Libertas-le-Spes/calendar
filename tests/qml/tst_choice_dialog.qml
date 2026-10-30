import QtQuick
import QtTest
import "../.."

Item {
  width: 400
  height: 300

  ChoiceDialog {
    id: dialog

    anchors.fill: parent
    firstText: "All events"
    secondText: "This event"
  }

  Item {
    id: elsewhere
    focus: true
  }

  SignalSpy { id: canceledSpy; target: dialog; signalName: "canceled" }

  TestCase {
    name: "ChoiceDialog"
    when: windowShown

    function init() {
      canceledSpy.clear()
      dialog.opened = false
      elsewhere.forceActiveFocus()
      dialog.opened = true
      tryVerify(function() { return dialog.buttons[2].activeFocus })
    }

    function screenX(button) {
      return button.mapToItem(dialog, 0, 0).x
    }

    function test_the_buttons_are_listed_in_the_order_they_stand_on_screen() {
      verify(screenX(dialog.buttons[0]) < screenX(dialog.buttons[1]))
      verify(screenX(dialog.buttons[1]) < screenX(dialog.buttons[2]))
    }

    function test_escape_cancels() {
      keyClick(Qt.Key_Escape)
      compare(canceledSpy.count, 1)
    }

    function test_left_moves_to_the_button_on_the_left_and_right_back() {
      keyClick(Qt.Key_Left)
      verify(dialog.buttons[1].activeFocus)
      keyClick(Qt.Key_Left)
      verify(dialog.buttons[0].activeFocus)
      keyClick(Qt.Key_Right)
      verify(dialog.buttons[1].activeFocus)
    }
  }
}

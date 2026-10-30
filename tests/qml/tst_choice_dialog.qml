import QtQuick
import QtTest
import qs.Ui
import "../.."

Item {
  width: 400
  height: 300

  Button {
    id: before
    focusable: true
  }

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

  Button {
    id: behind
    focusable: true
  }

  SignalSpy { id: canceledSpy; target: dialog; signalName: "canceled" }
  SignalSpy { id: firstSpy; target: dialog; signalName: "first" }
  SignalSpy { id: secondSpy; target: dialog; signalName: "second" }

  TestCase {
    name: "ChoiceDialog"
    when: windowShown

    function init() {
      canceledSpy.clear()
      firstSpy.clear()
      secondSpy.clear()
      dialog.opened = false
      elsewhere.forceActiveFocus()
      dialog.opened = true
      tryVerify(function() { return dialog.Window.activeFocusItem !== elsewhere })
    }

    function inside() {
      for (var i = 0; i < dialog.buttons.length; i++)
        if (dialog.buttons[i].activeFocus) return true
      return false
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

    function test_it_opens_on_cancel() {
      verify(dialog.buttons[0].activeFocus)
    }

    function test_enter_right_after_opening_cancels_and_answers_nothing() {
      keyClick(Qt.Key_Return)
      compare(canceledSpy.count, 1)
      compare(firstSpy.count, 0)
      compare(secondSpy.count, 0)
    }

    function test_space_right_after_opening_cancels_and_answers_nothing() {
      keyClick(Qt.Key_Space)
      compare(canceledSpy.count, 1)
      compare(firstSpy.count, 0)
      compare(secondSpy.count, 0)
    }

    function test_right_moves_to_the_button_on_the_right_and_left_back() {
      keyClick(Qt.Key_Right)
      verify(dialog.buttons[1].activeFocus)
      keyClick(Qt.Key_Right)
      verify(dialog.buttons[2].activeFocus)
      keyClick(Qt.Key_Left)
      verify(dialog.buttons[1].activeFocus)
    }

    function pressFromEveryButton(key, modifiers) {
      for (var i = 0; i < dialog.buttons.length; i++) {
        dialog.buttons[i].forceActiveFocus()
        keyClick(key, modifiers)
        verify(inside(), "left the dialog from button " + i)
      }
    }

    function test_tab_walks_the_buttons_left_to_right_and_wraps() {
      keyClick(Qt.Key_Tab)
      verify(dialog.buttons[1].activeFocus)
      keyClick(Qt.Key_Tab)
      verify(dialog.buttons[2].activeFocus)
      keyClick(Qt.Key_Tab)
      verify(dialog.buttons[0].activeFocus)
    }

    function test_shift_tab_walks_the_buttons_right_to_left_and_wraps() {
      keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
      verify(dialog.buttons[2].activeFocus)
      keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
      verify(dialog.buttons[1].activeFocus)
      keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
      verify(dialog.buttons[0].activeFocus)
    }

    function test_tab_from_any_button_stays_inside_the_dialog() {
      pressFromEveryButton(Qt.Key_Tab, Qt.NoModifier)
    }

    function test_shift_tab_from_any_button_stays_inside_the_dialog() {
      pressFromEveryButton(Qt.Key_Backtab, Qt.ShiftModifier)
    }
  }
}

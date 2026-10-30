import QtQuick
import QtTest
import qs.Ui
import "../.."

Item {
  id: scene

  width: 400
  height: 400

  Item {
    id: dialog

    property bool opened: false
    property var keys: []

    function handleKey(event) {
      dialog.keys.push(event.key)
    }
  }

  FocusWalker {
    id: walker

    anchors.fill: parent
    opened: true
    confirmDialog: dialog
    formArea: form
    takesText: scene.takesText

    Column {
      Button { id: first; focusable: true }
      Button { id: second; focusable: true }

      Item {
        id: arrowOwner
        readonly property bool ownsArrows: true
        width: 40
        height: 20
        activeFocusOnTab: true
      }

      TextInput { id: field; width: 40; height: 20; activeFocusOnTab: true }

      Loader {
        id: loader
        active: false
        sourceComponent: Button { focusable: true }
      }

      Item {
        id: form
        width: 40
        height: 40
        Button { id: formFirst; focusable: true }
        Button { id: formLast; y: 20; focusable: true }
      }

      Button { id: afterForm; focusable: true }

      Flickable {
        id: scroller
        width: 40
        height: 30
        contentHeight: 200
        clip: true
        Button { id: farDown; y: 150; focusable: true }
      }
    }
  }

  SignalSpy { id: switchSpy; target: walker; signalName: "switchPanelRequested" }
  SignalSpy { id: itemSpy; target: walker; signalName: "itemStepRequested" }

  function takesText(item) {
    return item !== null && item !== walker.keyTarget && "cursorPosition" in item && !item.readOnly
  }

  TestCase {
    name: "FocusWalker"
    when: windowShown

    function init() {
      walker.opened = true
      walker.formOpen = false
      dialog.opened = false
      dialog.keys = []
      loader.active = false
      first.visible = true
      scroller.contentY = 0
      switchSpy.clear()
      itemSpy.clear()
      walker.keyTarget.forceActiveFocus()
      wait(0)
    }

    function test_tab_walks_forward_and_shift_tab_walks_back() {
      keyClick(Qt.Key_Tab)
      verify(first.activeFocus)
      keyClick(Qt.Key_Tab)
      verify(second.activeFocus)
      keyClick(Qt.Key_Tab, Qt.ShiftModifier)
      verify(first.activeFocus)
    }

    function test_the_arrows_walk_from_a_button() {
      first.forceActiveFocus()
      keyClick(Qt.Key_Right)
      verify(second.activeFocus)
      keyClick(Qt.Key_Up)
      verify(first.activeFocus)
    }

    function test_the_arrows_stay_with_a_control_that_owns_them() {
      arrowOwner.forceActiveFocus()
      keyClick(Qt.Key_Right)
      verify(arrowOwner.activeFocus)
    }

    function test_the_arrows_do_not_walk_from_the_panel_itself() {
      keyClick(Qt.Key_Right)
      verify(walker.keyTarget.activeFocus)
    }

    function test_a_hidden_control_hands_the_keys_back_to_the_panel() {
      first.forceActiveFocus()
      first.visible = false
      tryVerify(function() { return walker.keyTarget.activeFocus })
    }

    function test_a_control_whose_loader_unloads_hands_the_keys_back_to_the_panel() {
      loader.active = true
      loader.item.forceActiveFocus()
      loader.active = false
      tryVerify(function() { return walker.keyTarget.activeFocus })
    }

    function test_a_click_on_a_button_hands_the_keys_back_to_the_panel() {
      mouseClick(second)
      tryVerify(function() { return walker.keyTarget.activeFocus })
    }

    function test_a_click_on_a_text_field_keeps_the_keys_in_it() {
      mouseClick(field)
      wait(0)
      verify(field.activeFocus)
    }

    function test_tab_after_a_click_walks_and_is_not_taken_for_a_click() {
      mouseClick(second)
      tryVerify(function() { return walker.keyTarget.activeFocus })
      keyClick(Qt.Key_Tab)
      wait(0)
      verify(first.activeFocus)
    }

    function test_tab_from_the_last_form_control_wraps_to_the_first() {
      walker.formOpen = true
      formLast.forceActiveFocus()
      keyClick(Qt.Key_Tab)
      tryVerify(function() { return formFirst.activeFocus })
    }

    function test_the_arrows_from_the_last_form_control_wrap_to_the_first() {
      walker.formOpen = true
      formLast.forceActiveFocus()
      keyClick(Qt.Key_Down)
      verify(formFirst.activeFocus)
    }

    function test_shift_tab_from_the_first_form_control_wraps_to_the_last() {
      walker.formOpen = true
      formFirst.forceActiveFocus()
      keyClick(Qt.Key_Tab, Qt.ShiftModifier)
      tryVerify(function() { return formLast.activeFocus })
    }

    function test_focus_that_jumps_out_of_the_open_form_comes_back_to_the_nearest_form_control() {
      walker.formOpen = true
      formFirst.forceActiveFocus()
      afterForm.forceActiveFocus()
      tryVerify(function() { return formLast.activeFocus })
    }

    function test_ctrl_tab_asks_for_the_next_panel() {
      keyClick(Qt.Key_Tab, Qt.ControlModifier)
      compare(switchSpy.count, 1)
      compare(switchSpy.signalArguments[0][0], 1)
    }

    function test_ctrl_tab_stays_put_while_the_form_is_open() {
      walker.formOpen = true
      formFirst.forceActiveFocus()
      keyClick(Qt.Key_Tab, Qt.ControlModifier)
      compare(switchSpy.count, 0)
      verify(formFirst.activeFocus)
    }

    function test_while_the_delete_confirmation_is_open_its_keys_go_to_it_and_space_answers_like_enter() {
      dialog.opened = true
      keyClick(Qt.Key_Space)
      keyClick(Qt.Key_Tab)
      keyClick(Qt.Key_J)
      compare(dialog.keys, [Qt.Key_Return, Qt.Key_Tab, Qt.Key_J])
      verify(walker.keyTarget.activeFocus)
      compare(itemSpy.count, 0)
    }

    function test_j_and_k_step_through_the_day() {
      keyClick(Qt.Key_J)
      keyClick(Qt.Key_K)
      compare(itemSpy.count, 2)
      compare(itemSpy.signalArguments[0][0], 1)
      compare(itemSpy.signalArguments[1][0], -1)
    }

    function test_a_control_reached_below_the_view_is_scrolled_into_it() {
      farDown.forceActiveFocus(Qt.TabFocusReason)
      compare(scroller.contentY, 150 + farDown.height + 8 - scroller.height)
    }

    function test_nothing_is_moved_while_the_panel_is_closed() {
      walker.opened = false
      mouseClick(second)
      wait(0)
      verify(second.activeFocus)
    }
  }
}

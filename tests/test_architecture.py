import re
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent

TEXT_OPENER = re.compile(r"(?m)^[ \t]*(?:component \w+:\s*)?(Text|TextEdit)\s*\{")
TEXT_FORMAT = re.compile(r"textFormat:\s*([\w.]+)")

RICH_TEXT_ALLOWED = {
    ("QuickAdd.qml", "Text.StyledText"): "the quick-add highlight escapes & < > before adding its own tags",
}

SHELL_PATTERNS = (
    re.compile(r"""["'](?:/usr/bin/|/bin/)?(?:ba|z|da)?sh["']"""),
    re.compile(r"""["']-c["']"""),
    re.compile(r"shell\s*=\s*True"),
    re.compile(r"os\.(?:system|popen)\s*\("),
    re.compile(r"execDetached"),
)


def own_properties(source, opened_at):
    depth = 1
    index = opened_at
    own = []
    while depth:
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        elif depth == 1:
            own.append(character)
        index += 1
    return "".join(own)


def text_elements():
    for path in sorted(REPO.glob("*.qml")):
        source = path.read_text()
        for match in TEXT_OPENER.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            found = TEXT_FORMAT.search(own_properties(source, match.end()))
            text_format = ""
            if found:
                text_format = found.group(1)
            yield path.name, line, match.group(1), text_format


def sources():
    paths = sorted(REPO.glob("*.qml")) + sorted(REPO.glob("*.js")) + sorted((REPO / "sync" / "omarchy_calendar_sync").glob("*.py"))
    for path in paths:
        yield path.relative_to(REPO), path.read_text()


class TestTextIsPlain(unittest.TestCase):
    def test_every_text_element_shows_plain_text_unless_listed_with_its_reason(self):
        for name, line, kind, text_format in text_elements():
            with self.subTest(element="%s:%d" % (name, line)):
                if (name, text_format) in RICH_TEXT_ALLOWED:
                    continue
                self.assertEqual(text_format, kind + ".PlainText")

    def test_the_listed_rich_text_elements_still_exist(self):
        found = set()
        for name, _line, _kind, text_format in text_elements():
            found.add((name, text_format))
        for allowed in RICH_TEXT_ALLOWED:
            with self.subTest(allowed=allowed):
                self.assertIn(allowed, found)


class TestNoShell(unittest.TestCase):
    def test_no_process_is_started_through_a_shell(self):
        for path, source in sources():
            for pattern in SHELL_PATTERNS:
                with self.subTest(path=str(path), pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(source))


if __name__ == "__main__":
    unittest.main()


WORKFLOWS = REPO / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")


def workflow_texts():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        yield path.name, path.read_text()


class TestWorkflows(unittest.TestCase):
    def test_there_is_a_workflow_to_check(self):
        self.assertNotEqual(list(workflow_texts()), [])

    def test_every_workflow_may_only_read_the_repository(self):
        for name, text in workflow_texts():
            with self.subTest(workflow=name):
                self.assertRegex(text, r"(?m)^permissions:\n  contents: read\n(?!  )")

    def test_no_workflow_runs_code_from_a_fork_with_the_repositorys_rights(self):
        for name, text in workflow_texts():
            with self.subTest(workflow=name):
                self.assertNotIn("pull_request_target", text)
                self.assertNotIn("workflow_run", text)

    def test_every_action_is_pinned_to_a_commit(self):
        for name, text in workflow_texts():
            for used in re.findall(r"uses:\s*(\S+)", text):
                with self.subTest(workflow=name, action=used):
                    self.assertRegex(used, PINNED_ACTION)

    def test_every_container_image_is_pinned_to_a_digest(self):
        for name, text in workflow_texts():
            for image in re.findall(r"image:\s*(\S+)", text):
                with self.subTest(workflow=name, image=image):
                    self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")

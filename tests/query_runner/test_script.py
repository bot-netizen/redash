import os
import subprocess

from _pytest.monkeypatch import MonkeyPatch

from sqldesk.query_runner.script import query_to_script_path, run_script
from tests import BaseTestCase


class ScriptTestCase(BaseTestCase):
    """
    A `MonkeyPatch` that is undone when the test ends.

    It used to be a class attribute with no `undo()` anywhere, which meant
    `os.path.exists` was replaced with `lambda x: True` **for the rest of the
    process**. Nothing noticed for years because nothing later in the suite
    depended on it -- until something did: `os.makedirs` asks `path.exists` about
    each parent, believed the lie, skipped creating them, and then failed on the
    final `mkdir` with a FileNotFoundError naming a directory it had been told
    was already there. Twenty-five tests in another directory entirely, passing
    on their own and failing in the full suite.

    Per test rather than per class, because a patch shared between two tests is
    a patch whose lifetime nobody can read off the page.
    """

    def setUp(self):
        super().setUp()
        self.monkeypatch = MonkeyPatch()
        self.addCleanup(self.monkeypatch.undo)


class TestQueryToScript(ScriptTestCase):
    def test_unspecified(self):
        self.assertEqual("/foo/bar/baz.sh", query_to_script_path("*", "/foo/bar/baz.sh"))

    def test_specified(self):
        self.assertRaises(IOError, lambda: query_to_script_path("/foo/bar", "baz.sh"))

        self.monkeypatch.setattr(os.path, "exists", lambda x: True)
        self.assertEqual(["/foo/bar/baz.sh"], query_to_script_path("/foo/bar", "baz.sh"))


class TestRunScript(ScriptTestCase):
    def test_success(self):
        self.monkeypatch.setattr(subprocess, "check_output", lambda script, shell: "test")
        self.assertEqual(("test", None), run_script("/foo/bar/baz.sh", True))

    def test_failure(self):
        self.monkeypatch.setattr(subprocess, "check_output", lambda script, shell: None)
        self.assertEqual((None, "Error reading output"), run_script("/foo/bar/baz.sh", True))
        self.monkeypatch.setattr(subprocess, "check_output", lambda script, shell: "")
        self.assertEqual((None, "Empty output from script"), run_script("/foo/bar/baz.sh", True))
        self.monkeypatch.setattr(subprocess, "check_output", lambda script, shell: " ")
        self.assertEqual((None, "Empty output from script"), run_script("/foo/bar/baz.sh", True))


class TestThePatchDoesNotLeak(BaseTestCase):
    """
    The regression. `os.path.exists` lying for the rest of the process is the
    kind of fault that is invisible where it happens and baffling everywhere
    else, so it gets a test of its own rather than a comment.
    """

    def test_os_path_exists_still_tells_the_truth(self):
        self.assertFalse(os.path.exists("/definitely/not/a/real/path/here"))

    def test_and_makedirs_can_still_create_a_nested_directory(self):
        import shutil
        import tempfile

        root = tempfile.mkdtemp()
        try:
            nested = os.path.join(root, "one", "two")
            os.makedirs(nested, exist_ok=True)
            self.assertTrue(os.path.isdir(nested))
        finally:
            shutil.rmtree(root, ignore_errors=True)

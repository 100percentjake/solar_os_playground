from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "hacker-news" / "hacker_news.py"


class FakeTui(types.ModuleType):
    KEY_ESCAPE = 27
    KEY_LEFT = 1000
    KEY_RIGHT = 1001
    KEY_UP = 1002
    KEY_DOWN = 1003
    KEY_PAGE_UP = 1004
    KEY_PAGE_DOWN = 1005
    KEY_HOME = 1006
    KEY_END = 1007
    INVERSE = 1
    BOLD = 2

    def getch(self, timeout):
        return self.KEY_ESCAPE


def load_module():
    tui = FakeTui("solaros.tui")
    solaros = types.ModuleType("solaros")
    solaros.tui = tui
    solaros.should_exit = lambda: True
    sys.modules["solaros"] = solaros
    sys.modules["solaros.tui"] = tui
    spec = importlib.util.spec_from_file_location("hacker_news_app", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HackerNewsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_module()

    def test_hn_html_becomes_readable_text(self):
        rendered = self.app.html_to_text(
            "First &amp; second<p>code: &lt;x&gt;<br>done")
        self.assertEqual(rendered, "First & second\ncode: <x>\ndone")

    def test_domain_does_not_require_browser_navigation(self):
        self.assertEqual(self.app.domain("https://www.example.com/a?q=1"), "example.com")
        self.assertEqual(self.app.domain(""), "")

    def test_collapsed_subtree_is_removed_from_visible_nodes(self):
        grandchild = {"id": 3, "children": [], "loaded": True,
                      "collapsed": False}
        child = {"id": 2, "children": [grandchild], "loaded": True,
                 "collapsed": False}
        sibling = {"id": 4, "children": [], "loaded": True,
                   "collapsed": False}
        root = {"children": [child, sibling]}
        self.assertEqual([node["id"] for node in self.app.visible_nodes(root)],
                         [2, 3, 4])
        child["collapsed"] = True
        self.assertEqual([node["id"] for node in self.app.visible_nodes(root)],
                         [2, 4])


if __name__ == "__main__":
    unittest.main()

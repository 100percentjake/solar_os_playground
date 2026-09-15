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

    def test_large_json_integers_are_safe_on_solaros(self):
        parsed = self.app.safe_json_loads(
            b'{"id":45200001,"time":1758000000,"score":42,'
            b'"text":"number 1758000000","negative":-1073741825}')
        self.assertEqual(parsed["id"], 45200001)
        self.assertEqual(parsed["time"], "1758000000")
        self.assertEqual(parsed["score"], 42)
        self.assertEqual(parsed["text"], "number 1758000000")
        self.assertEqual(parsed["negative"], "-1073741825")

    def test_item_ids_are_not_converted_through_int(self):
        seen = []
        original = self.app.request_json
        self.app.request_json = lambda path: seen.append(path) or {"id": path}
        try:
            self.app.fetch_item("45200001")
            self.assertEqual(seen, ["item/45200001.json"])
            with self.assertRaisesRegex(RuntimeError, "invalid item id"):
                self.app.fetch_item("1/other")
        finally:
            self.app.request_json = original

    def test_http_response_with_hn_timestamp_uses_safe_decoder(self):
        class Http:
            @staticmethod
            def get(url, headers, timeout, limit, follow_redirects):
                return {"status_code": 200, "truncated": False,
                        "body": b'{"id":45200001,"time":1758000000}'}

        previous = getattr(self.app.solaros, "http", None)
        self.app.solaros.http = Http()
        try:
            item = self.app.request_json("item/45200001.json")
            self.assertEqual(item, {"id": 45200001, "time": "1758000000"})
        finally:
            if previous is None:
                del self.app.solaros.http
            else:
                self.app.solaros.http = previous

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

    def test_line_navigation_jumps_between_item_boundaries(self):
        starts = [0, 3, 9]
        self.assertEqual(self.app.item_at_line(starts, 7), 1)
        self.assertEqual(self.app.adjacent_item_line(starts, 7, 1), 9)
        self.assertEqual(self.app.adjacent_item_line(starts, 7, -1), 3)
        self.assertEqual(self.app.adjacent_item_line(starts, 3, -1), 0)

    def test_children_are_published_one_at_a_time(self):
        parent = {"depth": -1, "kid_ids": [1, 2], "children": [],
                  "loaded": False, "collapsed": False}
        original = self.app.fetch_item
        progress = []
        self.app.fetch_item = lambda item_id: {
            "id": item_id, "by": "user", "text": "comment", "kids": []}
        try:
            self.app.load_children(
                parent,
                lambda done, total: progress.append(
                    (done, total, len(parent["children"]))))
        finally:
            self.app.fetch_item = original
        self.assertEqual(progress, [(0, 2, 0), (1, 2, 1), (2, 2, 2)])

    def test_stories_are_redrawn_after_each_request(self):
        original_request = self.app.request_json
        original_fetch = self.app.fetch_item
        original_draw = self.app.draw_stories
        frames = []
        self.app.request_json = lambda path: [1, 2]
        self.app.fetch_item = lambda item_id: {
            "id": item_id, "type": "story", "title": "Story " + str(item_id)}
        self.app.draw_stories = lambda stories, scroll, name, **kwargs: frames.append(
            (len(stories), kwargs.get("loading")))
        try:
            result = self.app.fetch_stories("topstories", "Top")
        finally:
            self.app.request_json = original_request
            self.app.fetch_item = original_fetch
            self.app.draw_stories = original_draw
        self.assertEqual(len(result), 2)
        self.assertEqual(frames, [(0, (0, 2)), (1, (1, 2)), (2, (2, 2))])


if __name__ == "__main__":
    unittest.main()

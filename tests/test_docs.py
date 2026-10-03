import os
import re
import unittest

from sqldesk import features

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def page(name):
    with open(os.path.join(DOCS, name), encoding="utf-8") as f:
        return f.read()


class TestThePermissionsTable(unittest.TestCase):
    """
    The administration page lists the permissions an administrator hands to a
    group. A list of those written by hand is a list that goes stale the first
    time somebody adds a feature, and the way it goes stale is the bad way: a
    permission exists, nothing documents it, and nobody grants it because
    nobody knows it is there.
    """

    def listed(self):
        return set(re.findall(r"<code>([a-z_]+)</code></td><td>", page("guide/administration.html")))

    def test_lists_every_feature_there_is(self):
        named = {feature.name for feature in features.all_features()}

        self.assertEqual(self.listed() & named, named, "a feature exists that the docs do not mention")

    def test_and_invents_none(self):
        named = {feature.name for feature in features.all_features()}
        # Only the rows of that table; other `<code>` on the page is settings.
        invented = {one for one in self.listed() if one.startswith(("manage_", "use_", "keep_", "send_"))} - named

        self.assertEqual(invented, set())


class TestTheDeploymentDefaults(unittest.TestCase):
    """
    The deploying page tells somebody what is off until they ask for it. If a
    default moves and the page does not, the page is worse than nothing: it is
    a reason not to check.
    """

    def test_says_what_is_off_by_default(self):
        import yaml

        with open(os.path.join(os.path.dirname(DOCS), "charts", "sqldesk", "values.yaml"), encoding="utf-8") as f:
            values = yaml.safe_load(f)
        text = page("guide/deploying.html")

        for value, path in (
            ("mcp.enabled", ("mcp", "enabled")),
            ("streams.enabled", ("streams", "enabled")),
            ("uploads.enabled", ("uploads", "enabled")),
            ("rendering.enabled", ("rendering", "enabled")),
        ):
            at = values
            for key in path:
                at = at[key]
            self.assertFalse(at, "{} is no longer off by default".format(value))
            self.assertIn("<code>{}</code>".format(value), text)

import unittest
import urllib.error
import urllib.request
from unittest import mock

from omarchy_calendar_sync import web


def redirect(handler, new_address):
    request = urllib.request.Request("https://feeds.example.invalid/made-up.ics")
    return handler.redirect_request(request, None, 302, "Found", {}, new_address)


class TestPublicRedirects(unittest.TestCase):
    def test_a_redirect_to_another_https_address_is_followed(self):
        followed = redirect(web._HttpsOnlyRedirects(), "https://mirror.example.invalid/made-up.ics")
        self.assertEqual(followed.full_url, "https://mirror.example.invalid/made-up.ics")

    def test_a_redirect_down_to_http_is_refused(self):
        with self.assertRaises(web.RedirectRefused):
            redirect(web._HttpsOnlyRedirects(), "http://feeds.example.invalid/made-up.ics")

    def test_a_redirect_to_ftp_is_refused(self):
        with self.assertRaises(web.RedirectRefused):
            redirect(web._HttpsOnlyRedirects(), "ftp://feeds.example.invalid/made-up.ics")


class TestCredentialRedirects(unittest.TestCase):
    def test_even_a_redirect_to_https_is_refused(self):
        with self.assertRaises(web.RedirectRefused):
            redirect(web._NoRedirects(), "https://elsewhere.example.invalid/")


class TestSchemes(unittest.TestCase):
    def test_the_opener_can_speak_https_and_nothing_else(self):
        for redirects in (web._HttpsOnlyRedirects(), web._NoRedirects()):
            opener = web._opener(redirects)
            for handler in opener.handlers:
                for scheme in ("http", "file", "ftp", "data"):
                    with self.subTest(handler=type(handler).__name__, scheme=scheme):
                        self.assertFalse(hasattr(handler, scheme + "_open"))

    def test_every_address_that_is_not_https_fails_to_open(self):
        for address in ("file:///made/up", "ftp://made-up.example.invalid/x", "data:text/plain,made-up"):
            with self.subTest(address=address):
                with self.assertRaises(urllib.error.URLError):
                    web.open_public(urllib.request.Request(address), 1)
                with self.assertRaises(urllib.error.URLError):
                    web.open_with_credential(urllib.request.Request(address), 1)


class TestWhichOpenerIsUsed(unittest.TestCase):
    def opener_built_by(self, open_function):
        built = mock.Mock()
        with mock.patch.object(web, "_opener", autospec=True, return_value=built) as make:
            open_function(urllib.request.Request("https://made-up.example.invalid/"), 5)
        built.open.assert_called_once()
        return make.call_args.args[0]

    def test_a_request_carrying_a_credential_follows_no_redirect(self):
        self.assertIsInstance(self.opener_built_by(web.open_with_credential), web._NoRedirects)

    def test_a_public_request_follows_https_redirects_only(self):
        self.assertIsInstance(self.opener_built_by(web.open_public), web._HttpsOnlyRedirects)


if __name__ == "__main__":
    unittest.main()

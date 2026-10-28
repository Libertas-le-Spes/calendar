import unittest
import urllib.error
import urllib.request

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
    def test_every_address_that_is_not_https_fails_to_open(self):
        for address in ("http://127.0.0.1:9/", "file:///made/up", "ftp://127.0.0.1/x", "data:text/plain,made-up"):
            with self.subTest(address=address):
                with self.assertRaises(urllib.error.URLError):
                    web.open_public(urllib.request.Request(address), 1)
                with self.assertRaises(urllib.error.URLError):
                    web.open_with_credential(urllib.request.Request(address), 1)


if __name__ == "__main__":
    unittest.main()

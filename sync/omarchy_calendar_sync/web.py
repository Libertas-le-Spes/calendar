"""How the sync opens addresses on the web.

Only https is spoken: there is no handler for http, ftp, file or data, so
an address of any other kind fails to open rather than being fetched. A
redirect is followed only to another https address, and a request that
carries a credential follows no redirect at all, so the credential is sent
to the host it was meant for and nowhere else.
"""

import urllib.error
import urllib.parse
import urllib.request


class RedirectRefused(urllib.error.URLError):
    """A redirect led somewhere the sync does not follow."""


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise RedirectRefused("a redirect left https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectRefused("a request carrying a credential was redirected")


def _opener(redirects):
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPSHandler(),
        urllib.request.UnknownHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
        redirects,
    ):
        opener.add_handler(handler)
    return opener


def open_public(request, timeout):
    """Open a request that carries no credential beyond its address."""
    return _opener(_HttpsOnlyRedirects()).open(request, timeout=timeout)


def open_with_credential(request, timeout):
    """Open a request whose headers or body carry a credential."""
    return _opener(_NoRedirects()).open(request, timeout=timeout)

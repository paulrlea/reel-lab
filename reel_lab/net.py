import json
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


class RemoteError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, *, method='GET', payload=None, headers=None, raw=None, timeout=60):
    hdr = dict(headers or {})
    if payload is not None:
        raw = json.dumps(payload).encode()
        hdr['Content-Type'] = 'application/json'
    try:
        with build_opener(NoRedirect()).open(Request(url, data=raw, headers=hdr, method=method), timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        # Never log server-supplied messages, which may include tokens or URLs.
        code = ''
        try:
            error = json.load(exc).get('error', {})
            code = f" (API code {int(error['code'])})" if 'code' in error else ''
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
        raise RemoteError(f'HTTP {exc.code}{code}') from None
    except (URLError, TimeoutError, ValueError, OSError):
        raise RemoteError('Remote request failed or response was not valid JSON') from None
    if not isinstance(result, dict) or 'error' in result:
        raise RemoteError('Remote service returned an error')
    return result

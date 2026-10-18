"""SDK-supported HTTP transport using httpx's environment proxy handling.

Only opaque signed upload/download URLs reach this object; never log them.
"""
from types import SimpleNamespace

import httpx


class UploadTransport:
    def __init__(self):
        self.client = httpx.Client(follow_redirects=True)

    def _request(self,method,url,headers=None,content=None,timeout=None):
        if content is not None and not isinstance(content,bytes): content = b''.join(content)
        try:
            response = self.client.request(method,url,headers=headers,content=content,timeout=min(timeout or 30,30))
        except httpx.TimeoutException:
            raise TimeoutError('Object-storage transport timed out') from None
        except httpx.HTTPError:
            raise ConnectionError('Object-storage transport failed') from None
        return SimpleNamespace(status=response.status_code,content=response.content,headers=response.headers)

    def put(self,url,headers=None,content=None,*,timeout=None): return self._request('PUT',url,headers,content,timeout)
    def get(self,url,headers=None,*,timeout=None): return self._request('GET',url,headers,timeout=timeout)
    def post(self,url,headers=None,content=None,*,timeout=None): return self._request('POST',url,headers,content,timeout)

import re
import base64
import logging
import json
from typing import Any, Dict, Optional
from urllib.parse import urlparse, quote_plus
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):
    """DLHD (DaddyLive) URL extractor - Güncellenmiş versiyon"""

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"
        self._cached_base_url = None
        self._iframe_context = None

    def _get_headers_for_url(self, url: str, base_headers: dict) -> dict:
        headers = base_headers.copy()
        if "newkso.ru" in url or ".cfd" in url:
            if self._iframe_context:
                origin = f"https://{urlparse(self._iframe_context).netloc}"
                new_headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Referer': self._iframe_context,
                    'Origin': origin
                }
            else:
                new_headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Referer': "https://inattv1301.xyz",
                    'Origin': "https://inattv1301.xyz"
                }
            headers.update(new_headers)
        return headers

    async def _make_request(self, url: str, method: str = "GET", headers: dict = None, **kwargs):
        final_headers = self._get_headers_for_url(url, headers or {})
        return await super()._make_request(url, method, final_headers, **kwargs)

    async def extract(self, url: str, **kwargs) -> Dict[str, Any]:
        
        async def get_daddylive_base_url():
            if self._cached_base_url:
                return self._cached_base_url
            try:
                resp = await self._make_request("https://inattv1301.xyz/")
                base_url = str(resp.url).rstrip('/') + '/'
                self._cached_base_url = base_url
                return base_url
            except Exception:
                return "https://inattv1301.xyz/"

        def extract_channel_id(url: str) -> Optional[str]:
            patterns = [
                r'/premium(\d+)/mono\.m3u8$',
                r'/(?:watch|stream|cast|player)/stream-(\d+)\.php',
                r'(?:%2F|/)stream-(\d+)\.php',
                r'stream-(\d+)\.php',
            ]
            for p in patterns:
                m = re.search(p, url, re.IGNORECASE)
                if m:
                    return m.group(1)
            return None

        async def try_endpoint(baseurl: str, endpoint: str, channel_id: str):
            stream_url = f"{baseurl}{endpoint}stream-{channel_id}.php"
            origin = f"{urlparse(baseurl).scheme}://{urlparse(baseurl).netloc}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': baseurl,
                'Origin': origin
            }

            # Player sayfalarına git
            resp1 = await self._make_request(stream_url, headers=headers)
            player2_links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>.*Player\s*2', resp1.text, re.IGNORECASE)

            if not player2_links:
                raise ExtractorError("Player 2 linki bulunamadı")

            url2 = baseurl.rstrip('/') + '/' + player2_links[0].lstrip('/')
            headers.update({'Referer': url2, 'Origin': url2})

            resp2 = await self._make_request(url2, headers=headers)
            iframe_urls = re.findall(r'iframe src="([^"]+)"', resp2.text)

            if not iframe_urls:
                raise ExtractorError("Iframe bulunamadı")

            iframe_url = iframe_urls[0]
            self._iframe_context = iframe_url

            iframe_resp = await self._make_request(iframe_url, headers=headers)
            content = iframe_resp.text

            # Auth Parametreleri Çıkar
            xjz = self._extract_xjz_format(content) or self._extract_bundle_format(content)

            if xjz:
                auth_host = xjz.get('b_host')
                auth_php = xjz.get('b_script')
                auth_ts = xjz.get('b_ts')
                auth_rnd = xjz.get('b_rnd')
                auth_sig = xjz.get('b_sig')
            else:
                auth_host = self._extract_var_old(content, 'a')
                auth_php = self._extract_var_old(content, 'b')
                auth_ts = self._extract_var_old(content, 'c')
                auth_rnd = self._extract_var_old(content, 'd')
                auth_sig = self._extract_var_old(content, 'e')

            channel_key_match = re.search(r'CHANNEL_KEY\s*=\s*["\']([^"\']+)["\']', content)
            channel_key = channel_key_match.group(1) if channel_key_match else None

            if not all([channel_key, auth_ts, auth_rnd, auth_sig, auth_host, auth_php]):
                raise ExtractorError("Auth parametreleri eksik")

            # Auth isteği
            if 'a.php' in (auth_php or '').lower():
                auth_php = '/auth.php'

            auth_url = f"{auth_host.rstrip('/')}/{auth_php.lstrip('/')}" + \
                      f"?channel_id={channel_key}&ts={auth_ts}&rnd={auth_rnd}&sig={quote_plus(auth_sig)}"

            await self._make_request(auth_url, headers=headers)

            # Server Lookup
            lookup_url = f"https://{urlparse(iframe_url).netloc}/server_lookup.php?channel_id={channel_key}"
            lookup_resp = await self._make_request(lookup_url, headers=headers)
            server_key = lookup_resp.json().get('server_key')

            if not server_key:
                raise ExtractorError("Server key alınamadı")

            # ==================== YENİ URL OLUŞTURMA ====================
            # Örnek: https://cyn.d72577a9dd0ec66.cfd/b2/mono.m3u8
            final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

            logger.info(f"Generated URL: {final_url}")

            stream_headers = {
                'User-Agent': headers['User-Agent'],
                'Referer': iframe_url,
                'Origin': f"https://{urlparse(iframe_url).netloc}"
            }

            return {
                "destination_url": final_url,
                "request_headers": stream_headers,
                "mediaflow_endpoint": self.mediaflow_endpoint,
            }

        # ===================== MAIN =====================
        try:
            channel_id = extract_channel_id(url)
            if not channel_id:
                raise ExtractorError("Channel ID bulunamadı")

            baseurl = await get_daddylive_base_url()
            endpoints = ["stream/", "cast/", "player/", "watch/"]

            for ep in endpoints:
                try:
                    return await try_endpoint(baseurl, ep, channel_id)
                except Exception as e:
                    logger.debug(f"{ep} denendi, hata: {e}")
                    continue

            raise ExtractorError("Tüm denemeler başarısız")

        except Exception as e:
            raise ExtractorError(f"DLHD Extract failed: {str(e)}")

    # ==================== HELPER ====================
    def _extract_var_old(self, js: str, name: str) -> Optional[str]:
        patterns = [
            rf'var (?:__)?{name}\s*=\s*atob\(["\']([^"\']+)["\']',
            rf'(?:var|let|const)\s+(?:__)?{name}\s*=\s*atob\s*\(\s*["\']([^"\']+)["\']',
        ]
        for p in patterns:
            m = re.search(p, js)
            if m:
                try:
                    return base64.b64decode(m.group(1)).decode('utf-8')
                except:
                    continue
        return None

    def _extract_xjz_format(self, js: str) -> Optional[Dict]:
        try:
            m = re.search(r'const\s+XJZ\s*=\s*["\']([^"\']+)["\']', js)
            if m:
                data = json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
                return {k: base64.b64decode(v).decode('utf-8') if isinstance(v, str) else v 
                        for k, v in data.items()}
        except:
            pass
        return None

    def _extract_bundle_format(self, js: str) -> Optional[Dict]:
        try:
            m = re.search(r'(?:const|var|let)\s+BUNDLE\s*=\s*["\']([^"\']+)["\']', js)
            if m:
                data = json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
                return {k: base64.b64decode(v).decode('utf-8') if isinstance(v, str) else v 
                        for k, v in data.items()}
        except:
            pass
        return None

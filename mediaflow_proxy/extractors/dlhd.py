import re
import logging
from urllib.parse import urlparse
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):
    """DLHD Extractor - inattv1301.xyz için optimize edilmiş"""

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"
        self._cached_base_url = None
        self._iframe_context = None

    async def extract(self, url: str, **kwargs):
        # Base URL
        base_url = "https://inattv1301.xyz/"
        logger.info(f"Base URL kullanılıyor: {base_url}")

        # Channel ID çıkar
        channel_id = self._extract_channel_id(url)
        if not channel_id:
            raise ExtractorError(f"Channel ID bulunamadı: {url}")

        logger.info(f"Channel ID: {channel_id}")

        endpoints = ["stream/", "cast/", "player/", "watch/"]

        for endpoint in endpoints:
            try:
                return await self._try_with_endpoint(base_url, endpoint, channel_id)
            except Exception as e:
                logger.warning(f"Endpoint {endpoint} başarısız: {e}")
                continue

        raise ExtractorError("Tüm endpoint'ler başarısız oldu.")

    def _extract_channel_id(self, url):
        match = re.search(r'stream-(\d+)', url, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'premium(\d+)', url)
        return match.group(1) if match else None

    async def _try_with_endpoint(self, base_url, endpoint, channel_id):
        page_url = f"{base_url}{endpoint}stream-{channel_id}.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
            'Referer': base_url,
        }

        logger.info(f"Sayfa deneniyor: {page_url}")

        # 1. Ana sayfa
        resp1 = await self._make_request(page_url, headers=headers)

        # 2. Player 2 bul
        player2_links = re.findall(r'href=["\']([^"\']+)["\'][^>]*>.*?(Player 2|2\. Player)', resp1.text, re.I)
        if not player2_links:
            raise ExtractorError("Player 2 linki bulunamadı")

        p2_url = base_url.rstrip('/') + '/' + player2_links[0][0].lstrip('/')
        headers['Referer'] = p2_url
        logger.info(f"Player 2 URL: {p2_url}")

        resp2 = await self._make_request(p2_url, headers=headers)

        # 3. Iframe
        iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)', resp2.text, re.I)
        if not iframe_match:
            raise ExtractorError("Iframe bulunamadı")

        iframe_url = iframe_match.group(1)
        self._iframe_context = iframe_url
        logger.info(f"Iframe URL: {iframe_url}")

        # Iframe içeriği
        iframe_resp = await self._make_request(iframe_url, headers=headers)
        content = iframe_resp.text

        # ===================== SERVER KEY BUL =====================
        server_key = self._find_server_key(content, iframe_url, channel_id)

        if not server_key:
            raise ExtractorError("Server key bulunamadı! (Tüm yöntemler denendi)")

        logger.info(f"✅ Server Key Bulundu: {server_key}")

        # Final M3U8
        final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

        stream_headers = {
            'User-Agent': headers['User-Agent'],
            'Referer': iframe_url,
            'Origin': f"https://{urlparse(iframe_url).netloc}"
        }

        logger.info(f"✅ Final Stream URL: {final_url}")

        return {
            "destination_url": final_url,
            "request_headers": stream_headers,
            "mediaflow_endpoint": self.mediaflow_endpoint,
        }

    def _find_server_key(self, content: str, iframe_url: str, channel_id: str):
        # Yöntem 1: Direkt JSON arama
        import json
        try:
            # server_key içeren JSON ara
            json_matches = re.findall(r'(\{[^}]*server_key[^}]*\})', content)
            for jm in json_matches:
                try:
                    data = json.loads(jm)
                    if 'server_key' in data:
                        return data['server_key']
                except:
                    continue
        except:
            pass

        # Yöntem 2: Regex ile
        patterns = [
            r'server_key["\']?\s*[:=]\s*["\']([^"\']+)',
            r'["\']([^"\']+\.d72577a9dd0ec66\.cfd)',
            r'https?://([a-zA-Z0-9-]+)\.d72577a9dd0ec66\.cfd',
            r'["\']([a-z0-9-]+)["\']',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                if m and len(m) > 2 and not m.startswith('http'):
                    logger.info(f"Regex ile bulundu: {m}")
                    return m

        # Yöntem 3: Server lookup
        try:
            netloc = urlparse(iframe_url).netloc
            lookup_url = f"https://{netloc}/server_lookup.php?channel_id={channel_id}"
            logger.info(f"Server lookup deneniyor: {lookup_url}")

            resp = await self._make_request(lookup_url, headers={'User-Agent': 'Mozilla/5.0'})
            data = resp.json()
            key = data.get('server_key')
            if key:
                logger.info(f"Lookup ile bulundu: {key}")
                return key
        except Exception as e:
            logger.warning(f"Lookup hatası: {e}")

        return None

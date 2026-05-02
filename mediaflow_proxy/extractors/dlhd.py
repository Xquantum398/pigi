import re
import logging
from urllib.parse import urlparse
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):
    """DLHD Extractor - Max Retries hatası için optimize edilmiş"""

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"
        self._cached_base_url = None
        self._iframe_context = None

    async def _make_request(self, url: str, method: str = "GET", headers: dict = None, **kwargs):
        """Daha toleranslı istek"""
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        if headers:
            default_headers.update(headers)

        # Retry ve timeout ekle
        kwargs.setdefault('timeout', 20)        # 20 saniye timeout
        kwargs.setdefault('max_retries', 3)

        return await super()._make_request(url, method, default_headers, **kwargs)

    async def extract(self, url: str, **kwargs):
        base_url = "https://inattv1301.xyz/"
        logger.info(f"Base URL: {base_url}")

        channel_id = self._extract_channel_id(url)
        if not channel_id:
            raise ExtractorError(f"Channel ID bulunamadı: {url}")

        logger.info(f"Channel ID: {channel_id}")

        endpoints = ["stream/", "cast/", "player/"]  # watch/ kaldırıldı, daha az istek

        for endpoint in endpoints:
            try:
                return await self._try_endpoint(base_url, endpoint, channel_id)
            except Exception as e:
                logger.warning(f"{endpoint} başarısız: {str(e)}")
                continue

        raise ExtractorError("Tüm denemeler başarısız oldu.")

    def _extract_channel_id(self, url):
        m = re.search(r'stream-(\d+)', url, re.I)
        if m:
            return m.group(1)
        m = re.search(r'premium(\d+)', url)
        return m.group(1) if m else None

    async def _try_endpoint(self, base_url, endpoint, channel_id):
        page_url = f"{base_url}{endpoint}stream-{channel_id}.php"
        logger.info(f"Denenen sayfa: {page_url}")

        headers = {'Referer': base_url}

        # 1. İlk sayfa
        resp1 = await self._make_request(page_url, headers=headers)

        # 2. Player 2 linki
        player2 = re.findall(r'href=["\']([^"\']+)["\'][^>]*>.*Player 2', resp1.text, re.I)
        if not player2:
            raise ExtractorError("Player 2 linki yok")

        p2_url = base_url.rstrip('/') + '/' + player2[0].lstrip('/')
        headers['Referer'] = p2_url

        resp2 = await self._make_request(p2_url, headers=headers)

        # 3. Iframe
        iframe_match = re.search(r'iframe[^>]+src=["\']([^"\']+)', resp2.text, re.I)
        if not iframe_match:
            raise ExtractorError("Iframe bulunamadı")

        iframe_url = iframe_match.group(1)
        self._iframe_context = iframe_url
        logger.info(f"Iframe: {iframe_url}")

        # Iframe içeriği (en kritik)
        iframe_resp = await self._make_request(iframe_url, headers=headers)
        content = iframe_resp.text

        # Server Key bul
        server_key = self._extract_server_key(content, iframe_url, channel_id)

        if not server_key:
            raise ExtractorError("Server key bulunamadı")

        logger.info(f"Server Key: {server_key}")

        final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

        stream_headers = {
            'User-Agent': headers.get('User-Agent', 'Mozilla/5.0...'),
            'Referer': iframe_url,
            'Origin': f"https://{urlparse(iframe_url).netloc}"
        }

        logger.info(f"✅ Final URL: {final_url}")

        return {
            "destination_url": final_url,
            "request_headers": stream_headers,
            "mediaflow_endpoint": self.mediaflow_endpoint,
        }

    def _extract_server_key(self, content: str, iframe_url: str, channel_id: str):
        # Regex yöntemleri
        patterns = [
            r'server_key["\']?\s*[:=]\s*["\']([^"\']+)',
            r'["\']([a-z0-9-]+)\.d72577a9dd0ec66\.cfd',
            r'https?://([a-z0-9-]+)\.d72577a9dd0ec66',
        ]

        for pattern in patterns:
            m = re.search(pattern, content)
            if m:
                key = m.group(1)
                logger.info(f"Server key regex ile bulundu: {key}")
                return key

        # Son çare: lookup
        try:
            netloc = urlparse(iframe_url).netloc
            lookup_url = f"https://{netloc}/server_lookup.php?channel_id={channel_id}"
            logger.info(f"Lookup deneniyor → {lookup_url}")
            
            resp = await self._make_request(lookup_url, headers={'User-Agent': 'Mozilla/5.0'})
            data = resp.json()
            return data.get('server_key')
        except Exception as e:
            logger.warning(f"Lookup failed: {e}")

        return None

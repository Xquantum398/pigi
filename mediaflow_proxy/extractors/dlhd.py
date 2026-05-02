import re
import logging
from urllib.parse import urlparse
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):
    """DLHD Extractor - cyn.d72577a9dd0ec66.cfd / zirve yapısına göre"""

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"

    async def extract(self, url: str, **kwargs):
        base_url = "https://inattv1301.xyz/"
        
        # Channel ID çıkar
        channel_match = re.search(r'stream-(\d+)', url, re.IGNORECASE)
        channel_id = channel_match.group(1) if channel_match else None

        if not channel_id:
            raise ExtractorError("Channel ID bulunamadı")

        logger.info(f"Channel ID: {channel_id}")

        try:
            # Player sayfası
            page_url = f"{base_url}player/stream-{channel_id}.php"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': base_url
            }

            resp1 = await self._make_request(page_url, headers=headers, timeout=30)

            # Player 2
            p2_match = re.search(r'href=["\']([^"\']+)"[^>]*>.*Player 2', resp1.text, re.I)
            if not p2_match:
                raise ExtractorError("Player 2 bulunamadı")

            p2_url = base_url.rstrip('/') + '/' + p2_match.group(1).lstrip('/')
            headers['Referer'] = p2_url

            resp2 = await self._make_request(p2_url, headers=headers, timeout=25)

            # Iframe
            iframe_match = re.search(r'iframe[^>]+src=["\']([^"\']+)', resp2.text, re.I)
            if not iframe_match:
                raise ExtractorError("Iframe bulunamadı")

            iframe_url = iframe_match.group(1)
            logger.info(f"Iframe: {iframe_url}")

            # İçerik al
            iframe_resp = await self._make_request(iframe_url, headers=headers, timeout=25)
            content = iframe_resp.text

            # Server Key Bul
            server_key = self._extract_server_key(content)
            if not server_key:
                raise ExtractorError("Server key bulunamadı")

            logger.info(f"Server Key: {server_key}")

            # **Çalışan format**
            final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

            logger.info(f"✅ Final URL: {final_url}")

            return {
                "destination_url": final_url,
                "request_headers": {
                    'User-Agent': headers['User-Agent'],
                    'Referer': iframe_url,
                    'Origin': f"https://{urlparse(iframe_url).netloc}"
                },
                "mediaflow_endpoint": self.mediaflow_endpoint,
            }

        except Exception as e:
            logger.error(f"Hata: {e}")
            raise ExtractorError(f"DLHD Extraction failed: {str(e)}")

    def _extract_server_key(self, content: str):
        """zirve tarzı server key çıkarma"""
        # 1. Tercih edilen yöntem
        m = re.search(r'server_key["\']?\s*[:=]\s*["\']([^"\']+)', content)
        if m:
            return m.group(1)

        # 2. Domain üzerinden
        m = re.search(r'([a-z0-9-]+)\.d72577a9dd0ec66\.cfd', content)
        if m:
            return m.group(1)

        # 3. Son çare
        m = re.search(r'["\']([a-z0-9]{3,20})["\']', content)
        if m:
            key = m.group(1)
            if len(key) >= 3 and key not in ['true','false','null']:
                return key

        return None

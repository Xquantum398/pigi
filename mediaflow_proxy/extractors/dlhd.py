import re
import logging
from urllib.parse import urlparse
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"

    async def extract(self, url: str, **kwargs):
        base_url = "https://inattv1301.xyz/"
        logger.info(f"Base URL: {base_url}")

        # Channel ID
        channel_id_match = re.search(r'stream-(\d+)', url, re.IGNORECASE)
        channel_id = channel_id_match.group(1) if channel_id_match else None

        if not channel_id:
            raise ExtractorError("Channel ID bulunamadı")

        logger.info(f"Channel ID: {channel_id}")

        # Ana akış
        try:
            # Player sayfası
            page_url = f"{base_url}player/stream-{channel_id}.php"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': base_url
            }

            resp1 = await self._make_request(page_url, headers=headers)
            
            # Player 2
            p2_match = re.search(r'href=["\']([^"\']+)"[^>]*>.*Player 2', resp1.text, re.I)
            if not p2_match:
                raise ExtractorError("Player 2 link bulunamadı")

            p2_url = base_url.rstrip('/') + '/' + p2_match.group(1).lstrip('/')
            headers['Referer'] = p2_url

            resp2 = await self._make_request(p2_url, headers=headers)

            # Iframe
            iframe_match = re.search(r'iframe[^>]+src=["\']([^"\']+)', resp2.text, re.I)
            if not iframe_match:
                raise ExtractorError("Iframe bulunamadı")

            iframe_url = iframe_match.group(1)
            logger.info(f"Iframe: {iframe_url}")

            # Iframe içeriği
            iframe_resp = await self._make_request(iframe_url, headers=headers)
            content = iframe_resp.text

            # Server Key Bul (zirve örneğine göre)
            server_key = self._extract_server_key(content)

            if not server_key:
                raise ExtractorError("Server key bulunamadı")

            logger.info(f"Server Key: {server_key}")

            # Final URL (çalışan yapı)
            final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

            logger.info(f"✅ Başarılı - Final URL: {final_url}")

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
            raise ExtractorError(f"DLHD Error: {str(e)}")

    def _extract_server_key(self, content: str):
        """zirve örneğine göre server key çıkarma"""
        # Yöntem 1: server_key direkt
        m = re.search(r'server_key["\']?\s*[:=]\s*["\']([^"\']+)', content)
        if m:
            return m.group(1)

        # Yöntem 2: .d72577a9dd0ec66.cfd olan subdomain
        m = re.search(r'([a-z0-9-]+)\.d72577a9dd0ec66\.cfd', content)
        if m:
            return m.group(1)

        # Yöntem 3: Son çare - herhangi bir kısa kelime (zirve gibi)
        m = re.search(r'["\']([a-z0-9]{3,15})["\']', content)
        if m:
            candidate = m.group(1)
            if candidate not in ['true', 'false', 'null', 'undefined']:
                return candidate

        return None

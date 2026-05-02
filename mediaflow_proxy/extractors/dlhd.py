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
        logger.info(f"🔥 Başlıyor - Base: {base_url}")

        channel_id = re.search(r'stream-(\d+)', url)
        channel_id = channel_id.group(1) if channel_id else None
        
        if not channel_id:
            raise ExtractorError("Channel ID yok")

        logger.info(f"Channel ID: {channel_id}")

        # Sadece en kritik endpoint
        test_url = f"{base_url}player/stream-{channel_id}.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36 Edg/147.0.0.0',
            'Referer': base_url,
            'Accept': 'text/html,application/xhtml+xml'
        }

        try:
            logger.info(f"1. Sayfa isteği: {test_url}")
            resp1 = await self._make_request(test_url, headers=headers, timeout=25)

            # Player 2 ara
            p2 = re.search(r'href=["\']([^"\']+Player[^"\']*)', resp1.text, re.I)
            if not p2:
                logger.error("Player 2 linki bulunamadı!")
                raise ExtractorError("Player 2 yok")

            p2_url = base_url.rstrip('/') + '/' + p2.group(1).lstrip('/')
            logger.info(f"2. Player 2 URL: {p2_url}")

            headers['Referer'] = p2_url
            resp2 = await self._make_request(p2_url, headers=headers, timeout=25)

            # Iframe
            iframe = re.search(r'<iframe[^>]*src=["\']([^"\']+)', resp2.text, re.I)
            if not iframe:
                logger.error("Iframe bulunamadı!")
                raise ExtractorError("Iframe yok")

            iframe_url = iframe.group(1)
            logger.info(f"3. Iframe URL: {iframe_url}")

            resp3 = await self._make_request(iframe_url, headers=headers, timeout=25)
            content = resp3.text

            # Server Key Arama (tüm olasılıklar)
            server_key = None
            for pattern in [r'server_key["\']?\s*[:=]\s*["\']([^"\']+)', 
                           r'([a-z0-9-]+)\.d72577a9dd0ec66\.cfd']:
                m = re.search(pattern, content)
                if m:
                    server_key = m.group(1)
                    break

            if not server_key:
                logger.error("❌ Server key bulunamadı!")
                logger.debug(f"Content snippet: {content[:800]}")
                raise ExtractorError("Server key yok")

            logger.info(f"✅ Server Key: {server_key}")

            final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"
            logger.info(f"✅ FINAL URL: {final_url}")

            return {
                "destination_url": final_url,
                "request_headers": {
                    'User-Agent': headers['User-Agent'],
                    'Referer': iframe_url
                },
                "mediaflow_endpoint": self.mediaflow_endpoint,
            }

        except Exception as e:
            logger.error(f"Genel Hata: {type(e).__name__} - {e}")
            raise ExtractorError(str(e))

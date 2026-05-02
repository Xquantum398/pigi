import re
import logging
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):

    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"

    async def extract(self, url: str, **kwargs):
        base_url = "https://inattv1301.xyz/"
        logger.info("DLHD Extractor başlatıldı")

        # Channel ID
        channel_id = re.search(r'stream-(\d+)', url)
        if not channel_id:
            raise ExtractorError("Channel ID bulunamadı")
        
        channel_id = channel_id.group(1)
        logger.info(f"Channel ID: {channel_id}")

        try:
            # Tek seferde player sayfasına git
            player_url = f"{base_url}player/stream-{channel_id}.php"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36 Edg/147.0.0.0',
                'Referer': https://inattv1301
            }

            logger.info(f"İstek atılıyor: {player_url}")
            resp = await self._make_request(player_url, headers=headers, timeout=30)

            text = resp.text

            # Server key ara (zirve tarzı)
            server_key = None
            match = re.search(r'server_key["\']?\s*[:=]\s*["\']([^"\']+)', text)
            if match:
                server_key = match.group(1)
            else:
                match = re.search(r'([a-z0-9-]+)\.d72577a9dd0ec66\.cfd', text)
                if match:
                    server_key = match.group(1)

            if not server_key:
                logger.error("Server key bulunamadı")
                raise ExtractorError("Server key yok")

            logger.info(f"Server Key bulundu: {server_key}")

            final_url = f"https://cyn.d72577a9dd0ec66.cfd/zirve/mono.m3u8"

            logger.info(f"✅ Oluşturulan Link: {final_url}")

            return {
                "destination_url": final_url,
                "request_headers": {
                    'User-Agent': headers['User-Agent'],
                    'Referer': player_url
                },
                "mediaflow_endpoint": self.mediaflow_endpoint,
            }

        except Exception as e:
            logger.error(f"Genel Hata: {e}")
            raise ExtractorError(str(e))

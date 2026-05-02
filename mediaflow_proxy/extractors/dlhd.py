import re
import logging
from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError

logger = logging.getLogger(__name__)


class DLHDExtractor(BaseExtractor):
    def __init__(self, request_headers: dict):
        super().__init__(request_headers)
        self.mediaflow_endpoint = "hls_manifest_proxy"

    async def extract(self, url: str, **kwargs):
        # Sadece channel ID çıkar
        channel_match = re.search(r'stream-(\d+)', url, re.IGNORECASE)
        if not channel_match:
            raise ExtractorError("Channel ID bulunamadı")
        
        channel_id = channel_match.group(1)
        logger.info(f"Channel ID: {channel_id}")

        # Geçici olarak sabit subdomain + server_key (zirve)
        # İleride server_key dinamik yapılabilir
        server_key = "zirve"   # veya "b2", "top1" vs. test edebilirsin

        final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

        logger.info(f"✅ Oluşturulan URL: {final_url}")

        return {
            "destination_url": final_url,
            "request_headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://inattv1301.xyz/',
                'Origin': 'https://inattv1301.xyz'
            },
            "mediaflow_endpoint": self.mediaflow_endpoint,
        }

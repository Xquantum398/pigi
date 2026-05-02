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
        logger.info(f"DLHD Extractor - URL: {url}")

        # Channel ID / Key çıkarma (yeni ve eski format)
        channel_id = None

        # 1. channel.html?id=b3 formatı
        match = re.search(r'id=([a-zA-Z0-9]+)', url)
        if match:
            channel_id = match.group(1)

        # 2. Eski stream-123.php formatı
        if not channel_id:
            match = re.search(r'stream-(\d+)', url)
            if match:
                channel_id = match.group(1)

        if not channel_id:
            raise ExtractorError("Channel ID bulunamadı")

        logger.info(f"Channel ID/Key: {channel_id}")

        # Şimdilik en çok çalışan server_key'ler
        # İleride dinamik yapılabilir
        server_key = "zirve"   # En stabil olanı (senin verdiğin örnek)

        final_url = f"https://{server_key}.d72577a9dd0ec66.cfd/{server_key}/mono.m3u8"

        logger.info(f"✅ Oluşturulan Stream URL: {final_url}")

        return {
            "destination_url": final_url,
            "request_headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                'Referer': base_url,
                'Origin': base_url.rstrip('/')
            },
            "mediaflow_endpoint": self.mediaflow_endpoint,
        }

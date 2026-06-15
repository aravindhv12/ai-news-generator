import httpx
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class ScraperService:
    async def extract_og_image(self, url: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0, follow_redirects=True)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Check OpenGraph
                og_image = soup.find("meta", property="og:image")
                if og_image:
                    return og_image.get("content")
                    
                # Check Twitter
                twitter_image = soup.find("meta", name="twitter:image")
                if twitter_image:
                    return twitter_image.get("content")
                    
                # Fallback to first large image (simplified)
                images = soup.find_all("img")
                for img in images:
                    src = img.get("src")
                    if src and src.startswith("http"):
                        return src
                        
                return ""
        except Exception as e:
            logger.error(f"Error scraping image from {url}: {e}")
            return ""

scraper_service = ScraperService()

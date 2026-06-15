import feedparser
import httpx
import asyncio
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "OpenAI Blog": "https://openai.com/news/rss.xml",
    "Cloudflare": "https://blog.cloudflare.com/rss/",
}

class NewsCollector:
    async def fetch_rss(self, source_name: str, url: str) -> List[Dict]:
        logger.info(f"Fetching RSS from {source_name}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml"
        }
        try:
            async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
                response = await client.get(url, timeout=15.0)
                feed = feedparser.parse(response.text)
                
                results = []
                for entry in feed.entries:
                    results.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": source_name,
                        "content": entry.get("summary", "") or entry.get("description", ""),
                        "published_at": datetime.now() # Simplified for now
                    })
                return results
        except Exception as e:
            logger.error(f"Error fetching {source_name}: {e}")
            return []

    async def fetch_hacker_news(self) -> List[Dict]:
        logger.info("Fetching Hacker News")
        try:
            async with httpx.AsyncClient() as client:
                # Get top stories
                resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                story_ids = resp.json()[:10] # Top 10
                
                results = []
                for sid in story_ids:
                    story_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                    story = story_resp.json()
                    if story.get("url"):
                        results.append({
                            "title": story.get("title", ""),
                            "url": story.get("url", ""),
                            "source": "Hacker News",
                            "content": "",
                            "published_at": datetime.now()
                        })
                return results
        except Exception as e:
            logger.error(f"Error fetching Hacker News: {e}")
            return []

    async def collect_all(self) -> List[Dict]:
        tasks = []
        for name, url in RSS_FEEDS.items():
            tasks.append(self.fetch_rss(name, url))
        
        tasks.append(self.fetch_hacker_news())
        
        all_results = await asyncio.gather(*tasks)
        flat_results = [item for sublist in all_results for item in sublist]
        logger.info(f"Collected total of {len(flat_results)} stories")
        return flat_results

collector = NewsCollector()

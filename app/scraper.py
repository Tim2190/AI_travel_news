import feedparser
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self, rss_urls: List[str]):
        self.rss_urls = rss_urls

    def scrape(self) -> List[Dict]:
        all_news = []
        for url in self.rss_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    news_item = {
                        "title": entry.get("title", ""),
                        "original_text": entry.get("summary", entry.get("description", "")),
                        "source_name": feed.feed.get("title", url),
                        "source_url": entry.get("link", ""),
                        "image_url": self._extract_image(entry)
                    }
                    # If original_text is too short, try to fetch full content (optional/basic)
                    if len(news_item["original_text"]) < 200:
                        news_item["original_text"] = self._fetch_full_text(news_item["source_url"]) or news_item["original_text"]
                    
                    all_news.append(news_item)
            except Exception as e:
                logger.error(f"Error scraping RSS {url}: {str(e)}")
        return all_news

    def _extract_image(self, entry) -> str:
        # Try to find image in enclosures or media content
        if "enclosures" in entry:
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image"):
                    return enc.get("href")
        if "media_content" in entry:
            for media in entry.media_content:
                if media.get("medium") == "image":
                    return media.get("url")
        return None

    def _fetch_full_text(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            # Basic logic: get all paragraphs from article/main content
            # This is highly dependent on the source site structure
            paragraphs = soup.find_all("p")
            return "\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
        except:
            return None

# Example RSS feeds for tourism news (can be expanded)
TOURISM_RSS_FEEDS = [
    "https://tengritravel.kz/rss/", # Example Kazakhstani travel news
    "https://kapital.kz/rss/tourism",
]

scraper = NewsScraper(TOURISM_RSS_FEEDS)

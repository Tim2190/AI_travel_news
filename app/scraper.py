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
                logger.info(f"Checking RSS source: {url}")
                feed = feedparser.parse(url)
                logger.info(f"Found {len(feed.entries)} entries in {url}")
                for entry in feed.entries:
                    news_item = {
                        "title": entry.get("title", ""),
                        "original_text": entry.get("summary", entry.get("description", "")),
                        "source_name": feed.feed.get("title", url),
                        "source_url": entry.get("link", ""),
                        "image_url": self._extract_image(entry)
                    }
                    if not news_item["title"] or not news_item["source_url"]:
                        continue
                        
                    # If original_text is too short, try to fetch full content
                    if len(news_item["original_text"]) < 200:
                        logger.info(f"Text too short for '{news_item['title']}', fetching full content...")
                        full_text = self._fetch_full_text(news_item["source_url"])
                        if full_text:
                            news_item["original_text"] = full_text
                    
                    all_news.append(news_item)
            except Exception as e:
                logger.error(f"Error scraping RSS {url}: {str(e)}")
        
        logger.info(f"Total news gathered from all sources: {len(all_news)}")
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

# Расширенный список источников: Казахстан + Мировые новости туризма
TOURISM_RSS_FEEDS = [
    "https://tengritravel.kz/rss/",           # Казахстан
    "https://kapital.kz/rss/tourism",         # Бизнес-туризм КЗ
    "https://www.travelpulse.com/rss/news",    # Мировые новости (TravelPulse)
    "https://www.skift.com/feed/",             # Аналитика и новости (Skift)
    "https://www.travelweekly.com/RSS/Lead-Stories", # Индустрия (Travel Weekly)
]

scraper = NewsScraper(TOURISM_RSS_FEEDS)

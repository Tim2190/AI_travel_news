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
        
        # 1. Прямой скрапинг казахстанских сайтов
        all_news.extend(self._scrape_tengri_travel())
        all_news.extend(self._scrape_kapital_tourism())
        
        # 2. Мировые новости через RSS (стабильные источники)
        all_news.extend(self._scrape_rss())
        
        logger.info(f"Total news gathered from all sources: {len(all_news)}")
        return all_news

    def _scrape_tengri_travel(self) -> List[Dict]:
        logger.info("Direct scraping TengriTravel...")
        news = []
        try:
            url = "https://tengritravel.kz/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Находим основные блоки новостей (селекторы зависят от верстки)
            articles = soup.select(".tn-article-item")[:5] # Первые 5 новостей
            for art in articles:
                title_tag = art.select_one(".tn-article-title")
                link_tag = art.select_one("a")
                if title_tag and link_tag:
                    title = title_tag.get_text(strip=True)
                    link = "https://tengritravel.kz" + link_tag["href"] if not link_tag["href"].startswith("http") else link_tag["href"]
                    
                    full_text, image_url = self._fetch_full_text_and_image(link)
                    news.append({
                        "title": title,
                        "original_text": full_text or title,
                        "source_name": "TengriTravel",
                        "source_url": link,
                        "image_url": image_url
                    })
        except Exception as e:
            logger.error(f"Error scraping TengriTravel: {e}")
        return news

    def _scrape_kapital_tourism(self) -> List[Dict]:
        logger.info("Direct scraping Kapital Tourism...")
        news = []
        try:
            url = "https://kapital.kz/tourism"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            articles = soup.select(".main-news__item, .news-list__item")[:5]
            for art in articles:
                title_tag = art.select_one("a.main-news__title, a.news-list__title")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    link = "https://kapital.kz" + title_tag["href"] if not title_tag["href"].startswith("http") else title_tag["href"]
                    
                    full_text, image_url = self._fetch_full_text_and_image(link)
                    news.append({
                        "title": title,
                        "original_text": full_text or title,
                        "source_name": "Kapital Tourism",
                        "source_url": link,
                        "image_url": image_url
                    })
        except Exception as e:
            logger.error(f"Error scraping Kapital: {e}")
        return news

    def _scrape_rss(self) -> List[Dict]:
        rss_news = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        }
        for url in self.rss_urls:
            try:
                logger.info(f"Checking RSS source: {url}")
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200: continue
                
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:5]:
                    link = entry.get("link", "").strip()
                    if not link: continue
                    
                    full_text = self._fetch_full_text(link)
                    rss_news.append({
                        "title": entry.get("title", "").strip(),
                        "original_text": full_text or entry.get("summary", ""),
                        "source_name": feed.feed.get("title", "World News"),
                        "source_url": link,
                        "image_url": self._extract_image(entry)
                    })
            except Exception as e:
                logger.error(f"Error RSS {url}: {e}")
        return rss_news

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
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None
            soup = BeautifulSoup(response.content, "html.parser")
            paragraphs = soup.find_all("p")
            return "\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
        except:
            return None

    def _fetch_full_text_and_image(self, url: str):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None, None
            soup = BeautifulSoup(response.content, "html.parser")
            paragraphs = soup.find_all("p")
            text = "\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
            image_url = None
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                image_url = og.get("content")
            if not image_url:
                img = soup.find("img")
                if img and img.get("src"):
                    image_url = img.get("src")
            return text, image_url
        except:
            return None, None

# Казахстан и СНГ (русскоязычные/региональные источники)
rss_urls: List[str] = [
    "https://tengrinews.kz/kazakhstan_news.rss",   # Tengrinews
    "https://www.zakon.kz/rss.xml",               # Zakon.kz
    "https://www.inform.kz/rss",                  # Inform.kz
    "https://www.nur.kz/rss/",                    # Nur.kz
    "https://kapital.kz/rss/",                    # Kapital.kz
    "https://forbes.kz/rss",                      # Forbes.kz
    "https://inbusiness.kz/ru/rss",               # Inbusiness.kz
    "https://time.kz/rss",                        # Time.kz
    "https://orda.kz/feed/",                      # Orda.kz (WordPress feed)
    "https://www.lada.kz/rss.xml",                # Lada.kz
    "https://ulysmedia.kz/rss/",                  # Ulysmedia.kz
    "https://vlast.kz/rss",                       # Vlast.kz
    "https://kursiv.media/feed/",                 # Kursiv.media (WordPress feed)
    "https://kaztag.kz/rss",                      # KazTAG
    "https://arbat.media/rss",                    # Arbat.media
]

scraper = NewsScraper(rss_urls)

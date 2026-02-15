import feedparser
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Источники БЕЗ RSS: мониторинг через прямой парсинг страницы (селекторы под свой сайт)
# Добавляй сюда любые СМИ без RSS: укажи URL страницы со списком новостей и селекторы
DIRECT_SCRAPE_SOURCES: List[Dict] = [
    {
        "name": "TengriTravel",
        "url": "https://tengritravel.kz/",
        "article_selector": ".tn-article-item",
        "title_selector": ".tn-article-title",
        "link_selector": "a",
        "base_url": "https://tengritravel.kz",
    },
    {
        "name": "Kapital Tourism",
        "url": "https://kapital.kz/tourism",
        "article_selector": ".main-news__item, .news-list__item",
        "title_selector": "a.main-news__title, a.news-list__title",
        "link_selector": "a.main-news__title, a.news-list__title",
        "base_url": "https://kapital.kz",
    },
    # Пример добавления другого СМИ без RSS (раскомментируй и подставь селекторы):
    # {
    #     "name": "Название СМИ",
    #     "url": "https://example.com/news",
    #     "article_selector": ".news-item",
    #     "title_selector": "h2 a",
    #     "link_selector": "h2 a",
    #     "base_url": "https://example.com",
    # },
]


class NewsScraper:
    def __init__(self, rss_urls: List[str], direct_sources: List[Dict] = None):
        self.rss_urls = rss_urls
        self.direct_sources = direct_sources or DIRECT_SCRAPE_SOURCES

    def scrape(self) -> List[Dict]:
        all_news = []

        # 1. Прямой скрапинг СМИ без RSS (конфигурируемый список)
        for source in self.direct_sources:
            all_news.extend(self._scrape_direct_source(source))

        # 2. RSS-источники
        all_news.extend(self._scrape_rss())

        logger.info(f"Total news gathered from all sources: {len(all_news)}")
        return all_news

    def _scrape_direct_source(self, config: Dict) -> List[Dict]:
        """Парсит страницу со списком статей по селекторам (для СМИ без RSS)."""
        name = config.get("name", "Unknown")
        url = config.get("url")
        article_sel = config.get("article_selector")
        title_sel = config.get("title_selector")
        link_sel = config.get("link_selector", "a")
        base_url = config.get("base_url", "").rstrip("/")
        if not url or not article_sel or not title_sel:
            logger.warning(f"Direct source '{name}' skipped: missing url/article_selector/title_selector")
            return []
        news = []
        try:
            logger.info(f"Direct scraping {name}...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            articles = soup.select(article_sel)[:5]
            for art in articles:
                title_el = art.select_one(title_sel)
                link_el = art.select_one(link_sel) if link_sel else title_el
                if not title_el or not link_el:
                    continue
                title = title_el.get_text(strip=True)
                href = link_el.get("href", "")
                if not href:
                    continue
                link = (base_url + href) if href.startswith("/") else href
                if not link.startswith("http"):
                    link = base_url + "/" + link
                full_text, image_url = self._fetch_full_text_and_image(link)
                news.append({
                    "title": title,
                    "original_text": full_text or title,
                    "source_name": name,
                    "source_url": link,
                    "image_url": image_url,
                })
        except Exception as e:
            logger.error(f"Error scraping {name}: {e}")
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

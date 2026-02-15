import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Все источники — только прямой парсинг сайтов (без RSS).
# Селекторы подобраны под типичную вёрстку; если сайт обновился — поправь под актуальный HTML.
DIRECT_SCRAPE_SOURCES: List[Dict] = [
    # Путешествия
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
    # Tengrinews (главная)
    {
        "name": "Tengrinews",
        "url": "https://tengrinews.kz/",
        "article_selector": ".tn-main-news-item",
        "title_selector": "a.tn-link",
        "link_selector": "a.tn-link",
        "base_url": "https://tengrinews.kz",
    },
    # Zakon.kz
    {
        "name": "Zakon.kz",
        "url": "https://www.zakon.kz/",
        "article_selector": ".block-news-item, .news-item, article",
        "title_selector": "a",
        "link_selector": "a",
        "base_url": "https://www.zakon.kz",
    },
    # Inform.kz
    {
        "name": "Inform.kz",
        "url": "https://www.inform.kz/ru",
        "article_selector": ".article-item, .news-item, .item",
        "title_selector": "a, .title a",
        "link_selector": "a",
        "base_url": "https://www.inform.kz",
    },
    # Nur.kz
    {
        "name": "Nur.kz",
        "url": "https://www.nur.kz/",
        "article_selector": "article, .article-card, .news-item",
        "title_selector": "a[href*='/news/'], .title a, h2 a",
        "link_selector": "a",
        "base_url": "https://www.nur.kz",
    },
    # Kapital.kz (главная)
    {
        "name": "Kapital.kz",
        "url": "https://kapital.kz/",
        "article_selector": ".main-news__item, .news-list__item",
        "title_selector": "a.main-news__title, a.news-list__title",
        "link_selector": "a.main-news__title, a.news-list__title",
        "base_url": "https://kapital.kz",
    },
    # Forbes.kz
    {
        "name": "Forbes.kz",
        "url": "https://forbes.kz/",
        "article_selector": ".article-item, article, .news-item",
        "title_selector": "a, h2 a, .title a",
        "link_selector": "a",
        "base_url": "https://forbes.kz",
    },
    # Inbusiness.kz
    {
        "name": "Inbusiness.kz",
        "url": "https://inbusiness.kz/ru",
        "article_selector": ".news-item, article, .item",
        "title_selector": "a, .title a",
        "link_selector": "a",
        "base_url": "https://inbusiness.kz",
    },
    # Time.kz
    {
        "name": "Time.kz",
        "url": "https://time.kz/",
        "article_selector": ".news-item, article, .item",
        "title_selector": "a, h2 a",
        "link_selector": "a",
        "base_url": "https://time.kz",
    },
    # Orda.kz
    {
        "name": "Orda.kz",
        "url": "https://orda.kz/",
        "article_selector": ".post, article, .news-item",
        "title_selector": "a, .entry-title a, h2 a",
        "link_selector": "a",
        "base_url": "https://orda.kz",
    },
    # Lada.kz
    {
        "name": "Lada.kz",
        "url": "https://www.lada.kz/",
        "article_selector": ".news-item, article, .item",
        "title_selector": "a, .title a",
        "link_selector": "a",
        "base_url": "https://www.lada.kz",
    },
    # Ulysmedia.kz
    {
        "name": "Ulysmedia.kz",
        "url": "https://ulysmedia.kz/",
        "article_selector": ".news-item, article",
        "title_selector": "a, h2 a",
        "link_selector": "a",
        "base_url": "https://ulysmedia.kz",
    },
    # Vlast.kz
    {
        "name": "Vlast.kz",
        "url": "https://vlast.kz/",
        "article_selector": ".article-item, article, .news-item",
        "title_selector": "a, .title a",
        "link_selector": "a",
        "base_url": "https://vlast.kz",
    },
    # Kursiv.media
    {
        "name": "Kursiv.media",
        "url": "https://kursiv.media/news",
        "article_selector": ".article-item, article, .news-item",
        "title_selector": "a, h2 a",
        "link_selector": "a",
        "base_url": "https://kursiv.media",
    },
    # KazTAG
    {
        "name": "KazTAG",
        "url": "https://kaztag.kz/ru",
        "article_selector": ".news-item, article, .item",
        "title_selector": "a, .title a",
        "link_selector": "a",
        "base_url": "https://kaztag.kz",
    },
    # Arbat.media
    {
        "name": "Arbat.media",
        "url": "https://arbat.media/",
        "article_selector": ".news-item, article, .post",
        "title_selector": "a, h2 a",
        "link_selector": "a",
        "base_url": "https://arbat.media",
    },
]


class NewsScraper:
    def __init__(self, direct_sources: List[Dict] = None):
        self.direct_sources = direct_sources or DIRECT_SCRAPE_SOURCES

    def scrape(self) -> List[Dict]:
        all_news = []
        for source in self.direct_sources:
            all_news.extend(self._scrape_direct_source(source))
        logger.info(f"Total news gathered from direct sources: {len(all_news)}")
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
                full_text, image_url, published_at = self._fetch_full_text_and_image(link)
                news.append({
                    "title": title,
                    "original_text": full_text or title,
                    "source_name": name,
                    "source_url": link,
                    "image_url": image_url,
                    "published_at": published_at,
                })
        except Exception as e:
            logger.error(f"Error scraping {name}: {e}")
        return news

    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Извлекает дату/время публикации со страницы статьи."""
        # Open Graph / Schema
        for prop in ("article:published_time", "published_time", "date"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                return self._parse_date(meta["content"])
        # <time datetime="...">
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            return self._parse_date(time_el["datetime"])
        # data-published, data-date
        for attr in ("data-published", "data-date", "data-time"):
            el = soup.find(attrs={attr: True})
            if el and el.get(attr):
                return self._parse_date(el[attr])
        return None

    def _parse_date(self, value: str) -> Optional[datetime]:
        if not value or not value.strip():
            return None
        value = value.strip()[:25]  # ISO часто YYYY-MM-DDTHH:MM:SS+00:00
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                if "+" in value or value.count("-") >= 2:
                    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
                else:
                    d = datetime.strptime(value[:10], "%Y-%m-%d")
                if d.tzinfo:
                    d = d.astimezone(timezone.utc).replace(tzinfo=None)
                return d
            except (ValueError, TypeError):
                continue
        return None

    def _fetch_full_text_and_image(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None, None, None
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
            published_at = self._extract_publish_date(soup)
            return text, image_url, published_at
        except Exception:
            return None, None, None

scraper = NewsScraper()

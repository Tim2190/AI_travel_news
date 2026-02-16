import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ ФИЛЬТРАЦИИ (РАСШИРЕННЫЕ) ---
TARGET_KEYWORDS = [
    # Туризм и Авиа (Основа)
    "туризм", "путешестви", "авиа", "рейс", "курорт", "виза", "шенген", 
    "отдых", "самолет", "границ", "отель", "flyarystan", "air astana", 
    "поезд", "билет", "паспорт", "безвиз", "scat", "qazaq air",
    # Экономика и Политика (Для контекста)
    "тенге", "налог", "бюджет", "инвестиц", "токаев", "министр", 
    "закон", "парламент", "правительств", "банк", "ввп", "инфляци",
    # Общие темы (Чтобы ловить больше новостей для "Сноба")
    "казахстан", "астана", "алматы", "шымкент", "қоғам", "сұхбат", 
    "жоба", "өзгеріс", "тарих", "мәдениет", "экология", "ауа райы", "климат",
    "образовани", "медицина", "технологи", "цифр", "internet", "связь"
]

# Все источники — только прямой парсинг сайтов (без RSS).
# ИСТОЧНИКИ: ЛЕНТЫ НОВОСТЕЙ (FEED)
# Ссылки ведут на страницы "Все новости" или "Лента", где контент обновляется хронологически.
DIRECT_SCRAPE_SOURCES: List[Dict] = [
    # --- ПРОФИЛЬНЫЕ (Туризм) ---
    {
        "name": "TengriTravel",
        "url": "https://tengritravel.kz/", # У них лента прямо на главной
        "article_selector": ".tn-article-item", 
        "title_selector": ".tn-article-title",
        "link_selector": "a",
        "base_url": "https://tengritravel.kz",
    },
    {
        "name": "Kapital Tourism",
        "url": "https://kapital.kz/tourism",
        "article_selector": ".news-list__item", # Селектор списка
        "title_selector": "a.news-list__title",
        "link_selector": "a.news-list__title",
        "base_url": "https://kapital.kz",
    },

    # --- ЛЕНТЫ НОВОСТЕЙ СМИ (ОБЩИЕ) ---
    {
        "name": "Tengrinews (Лента)",
        "url": "https://tengrinews.kz/news/", # Лента, а не главная
        "article_selector": ".tn-article-item",
        "title_selector": "span.tn-article-title",
        "link_selector": "a.tn-article-item",
        "base_url": "https://tengrinews.kz",
    },
    {
        "name": "Zakon (Лента)",
        "url": "https://www.zakon.kz/news/",
        "article_selector": ".z-card-news, .news-item",
        "title_selector": ".z-card-news__title a, a",
        "link_selector": "a",
        "base_url": "https://www.zakon.kz",
    },
    {
        "name": "Inform (Лента)",
        "url": "https://www.inform.kz/ru/lenta",
        "article_selector": ".lenta_news_item, .article-item",
        "title_selector": "a.title, .article-item__title",
        "link_selector": "a",
        "base_url": "https://www.inform.kz",
    },
    {
        "name": "Nur (Последние)",
        "url": "https://www.nur.kz/latest/",
        "article_selector": ".article-card",
        "title_selector": "a.article-card__title",
        "link_selector": "a.article-card__title",
        "base_url": "https://www.nur.kz",
    },
    {
        "name": "Kapital (Все)",
        "url": "https://kapital.kz/all",
        "article_selector": ".news-list__item",
        "title_selector": "a.news-list__title",
        "link_selector": "a.news-list__title",
        "base_url": "https://kapital.kz",
    },
    {
        "name": "Forbes (Лента)",
        "url": "https://forbes.kz/news",
        "article_selector": ".news-list__item, .news-item",
        "title_selector": ".news-list__title a, .title a",
        "link_selector": "a",
        "base_url": "https://forbes.kz",
    },
    {
        "name": "Inbusiness (Лента)",
        "url": "https://inbusiness.kz/ru/last",
        "article_selector": ".news-item, .item",
        "title_selector": "a.title, .title a",
        "link_selector": "a",
        "base_url": "https://inbusiness.kz",
    },
    {
        "name": "Time (Лента)",
        "url": "https://time.kz/news",
        "article_selector": ".news-item",
        "title_selector": "a.news-link",
        "link_selector": "a",
        "base_url": "https://time.kz",
    },
    {
        "name": "Orda (Главная/Лента)",
        "url": "https://orda.kz/ru/",
        "article_selector": ".main-feed-item, .post-item", # Актуальный селектор ленты
        "title_selector": "a.main-feed-title, h3 a",
        "link_selector": "a",
        "base_url": "https://orda.kz",
    },
    {
        "name": "Lada (Все)",
        "url": "https://www.lada.kz/all",
        "article_selector": ".news-item, .article",
        "title_selector": ".news-title a, a.title",
        "link_selector": "a",
        "base_url": "https://www.lada.kz",
    },
    {
        "name": "Ulysmedia (Новости)",
        "url": "https://ulysmedia.kz/news/",
        "article_selector": ".news-item, .feed-item",
        "title_selector": "a.news-title, h3 a",
        "link_selector": "a",
        "base_url": "https://ulysmedia.kz",
    },
    {
        "name": "Vlast (Новости)",
        "url": "https://vlast.kz/novosti/",
        "article_selector": ".article-item, .news-item",
        "title_selector": "a",
        "link_selector": "a",
        "base_url": "https://vlast.kz",
    },
    {
        "name": "Kursiv (Лента)",
        "url": "https://kz.kursiv.media/news/",
        "article_selector": ".post-card, .news-item",
        "title_selector": "h3 a, .title a",
        "link_selector": "a",
        "base_url": "https://kz.kursiv.media",
    },
    {
        "name": "KazTAG (Лента)",
        "url": "https://kaztag.kz/ru/news/",
        "article_selector": ".news-item, .article",
        "title_selector": ".title a, a",
        "link_selector": "a",
        "base_url": "https://kaztag.kz",
    },
    {
        "name": "ArbatMedia (Новости)",
        "url": "https://arbatmedia.kz/news-kz", # Новый домен
        "article_selector": ".news-card, .post-item",
        "title_selector": "h3 a, .title a",
        "link_selector": "a",
        "base_url": "https://arbatmedia.kz",
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
            
            # --- ИЗМЕНЕНИЕ: БЕРЕМ ТОП-20, А НЕ 5 ---
            articles = soup.select(article_sel)[:20] 
            
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

                # --- ФИЛЬТРАЦИЯ ---
                is_specialized_source = "tourism" in url or "travel" in url
                title_lower = title.lower()
                has_keyword = any(k in title_lower for k in TARGET_KEYWORDS)

                if not is_specialized_source and not has_keyword:
                    continue

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
        for prop in ("article:published_time", "published_time", "date"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                return self._parse_date(meta["content"])
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            return self._parse_date(time_el["datetime"])
        for attr in ("data-published", "data-date", "data-time"):
            el = soup.find(attrs={attr: True})
            if el and el.get(attr):
                return self._parse_date(el[attr])
        return None

    def _parse_date(self, value: str) -> Optional[datetime]:
        if not value or not value.strip():
            return None
        value = value.strip()[:25]
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

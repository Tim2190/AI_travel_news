import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ИСТОЧНИКИ: ОФИЦИАЛЬНЫЕ САЙТЫ ГОСУДАРСТВЕННЫХ ОРГАНОВ (РУССКИЕ ВЕРСИИ)
DIRECT_SCRAPE_SOURCES: List[Dict] = [
    # --- ВЫСШЕЕ РУКОВОДСТВО ---
    {
        "name": "Akorda (Президент)",
        "url": "https://www.akorda.kz/ru/events",
        "article_selector": ".event-item, .news-list__item",
        "title_selector": "h3 a, .title a, a",
        "link_selector": "h3 a, .title a, a",
        "base_url": "https://www.akorda.kz",
    },
    {
        "name": "PrimeMinister (Правительство)",
        "url": "https://primeminister.kz/ru/news",
        "article_selector": ".news_item, .card, .post-item",
        "title_selector": ".news_title a, .card-title a, a",
        "link_selector": "a",
        "base_url": "https://primeminister.kz",
    },

    # --- МИНИСТЕРСТВА (GOV.KZ - Единая платформа) ---
    {
        "name": "МинНацЭкономики",
        "url": "https://www.gov.kz/memleket/entities/economy/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинФин",
        "url": "https://www.gov.kz/memleket/entities/minfin/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МИД РК",
        "url": "https://www.gov.kz/memleket/entities/mfa/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МВД РК",
        "url": "https://www.gov.kz/memleket/entities/qriim/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинТруда",
        "url": "https://www.gov.kz/memleket/entities/enbek/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинЗдрав",
        "url": "https://www.gov.kz/memleket/entities/dsm/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинПросвещения",
        "url": "https://www.gov.kz/memleket/entities/edu/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинНауки",
        "url": "https://www.gov.kz/memleket/entities/sci/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинПромСтрой",
        "url": "https://www.gov.kz/memleket/entities/mps/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинТранспорт",
        "url": "https://www.gov.kz/memleket/entities/transport/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинЦифры",
        "url": "https://www.gov.kz/memleket/entities/mdai/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинКультуры",
        "url": "https://www.gov.kz/memleket/entities/mam/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинТуризм",
        "url": "https://www.gov.kz/memleket/entities/tsm/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинЭкологии",
        "url": "https://www.gov.kz/memleket/entities/ecogeo/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинСельХоз",
        "url": "https://www.gov.kz/memleket/entities/moa/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинЭнерго",
        "url": "https://www.gov.kz/memleket/entities/energo/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинЮст",
        "url": "https://www.gov.kz/memleket/entities/adilet/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МЧС РК",
        "url": "https://www.gov.kz/memleket/entities/emer/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "МинТорговли",
        "url": "https://www.gov.kz/memleket/entities/mti/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },

    # --- АКИМАТЫ МЕГАПОЛИСОВ ---
    {
        "name": "Акимат Алматы",
        "url": "https://www.gov.kz/memleket/entities/almaty/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
    },
    {
        "name": "Акимат Астаны",
        "url": "https://www.gov.kz/memleket/entities/astana/press/news?lang=ru",
        "article_selector": ".showcase-item",
        "title_selector": ".showcase-item__title",
        "link_selector": "a.showcase-item__title",
        "base_url": "https://www.gov.kz",
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
        """Парсит страницу со списком статей по селекторам."""
        name = config.get("name", "Unknown")
        url = config.get("url")
        article_sel = config.get("article_selector")
        title_sel = config.get("title_selector")
        link_sel = config.get("link_selector", "a")
        base_url = config.get("base_url", "").rstrip("/")
        
        if not url or not article_sel or not title_sel:
            logger.warning(f"Direct source '{name}' skipped: missing config")
            return []
            
        news = []
        try:
            logger.info(f"Direct scraping {name}...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Берем первые 20 новостей из ленты
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

                # ФИЛЬТРАЦИЯ ПО КЛЮЧЕВЫМ СЛОВАМ УДАЛЕНА ПО ЗАПРОСУ ПОЛЬЗОВАТЕЛЯ
                # Собираем всё подряд из указанных источников.

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
        """Извлекает дату публикации."""
        for prop in ("article:published_time", "published_time", "date"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                return self._parse_date(meta["content"])
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            return self._parse_date(time_el["datetime"])
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
            except:
                continue
        return None

    def _fetch_full_text_and_image(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None, None, None
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Собираем основной текст статьи
            paragraphs = soup.find_all("p")
            text = "\n".join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
            
            # Картинка
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

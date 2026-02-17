import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import logging
import urllib3
from typing import List, Dict, Optional, Tuple
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Playwright — только для gov.kz (получение токенов)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Отключаем надоедливые предупреждения о SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        "gov_kz": False,
    },
    {
        "name": "PrimeMinister (Правительство)",
        "url": "https://primeminister.kz/ru/news",
        "article_selector": ".news_item, .card, .post-item",
        "title_selector": ".news_title a, .card-title a, a",
        "link_selector": "a",
        "base_url": "https://primeminister.kz",
        "gov_kz": False,
    },
    # --- МИНИСТЕРСТВА (GOV.KZ - SPA) ---
    {"name": "МинНацЭкономики", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "economy"},
    {"name": "МинФин", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "minfin"},
    {"name": "МИД РК", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "mfa"},
    {"name": "МВД РК", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "qriim"},
    {"name": "МинТруда", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "enbek"},
    {"name": "МинЗдрав", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "dsm"},
    {"name": "МинПросвещения", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "edu"},
    {"name": "МинНауки", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "sci"},
    {"name": "МинПромСтрой", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "mps"},
    {"name": "МинТранспорт", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "transport"},
    {"name": "МинЦифры", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "mdai"},
    {"name": "МинКультуры", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "mam"},
    {"name": "МинТуризм", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "tsm"},
    {"name": "МинЭкологии", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "ecogeo"},
    {"name": "МинСельХоз", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "moa"},
    {"name": "МинЭнерго", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "energo"},
    {"name": "МинЮст", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "adilet"},
    {"name": "МЧС РК", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "emer"},
    {"name": "МинТорговли", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "mti"},
    # --- АКИМАТЫ ---
    {"name": "Акимат Алматы", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "almaty"},
    {"name": "Акимат Астаны", "url": "...", "base_url": "https://www.gov.kz", "gov_kz": True, "project": "astana"},
]

_gov_kz_tokens: Optional[Dict] = None

async def _fetch_gov_kz_tokens() -> Optional[Dict]:
    """Асинхронная функция получения токенов (запускается в отдельном потоке)"""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    tokens = {}
    try:
        async with async_playwright() as p:
            # Запускаем Chromium
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}, locale="ru-RU"
            )
            page = await context.new_page()
            
            # Ловушка для токенов
            def handle_request(request):
                if "api/v1/public/content-manager/news" in request.url:
                    h = request.headers
                    if h.get("hash") and h.get("token"):
                        tokens["hash"] = h["hash"]
                        tokens["token"] = h["token"]
                        tokens["user-agent"] = h.get("user-agent", "")
            
            page.on("request", handle_request)
            
            # Заходим на сайт
            try:
                await page.goto("https://www.gov.kz/memleket/entities/economy/press/news?lang=ru", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000) 
            except Exception:
                pass 
            
            await browser.close()
    except Exception as e:
        logger.error(f"Playwright error: {e}")
        return None
    return tokens if tokens else None

def run_async_in_thread(coro):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()

class NewsScraper:
    def __init__(self, direct_sources: List[Dict] = None):
        self.direct_sources = direct_sources or DIRECT_SCRAPE_SOURCES

    def scrape(self) -> List[Dict]:
        all_news = []
        
        # 1. Обычные источники
        regular_sources = [s for s in self.direct_sources if not s.get("gov_kz")]
        for source in regular_sources:
            all_news.extend(self._scrape_direct_source(source))

        # 2. Gov.kz источники
        gov_sources = [s for s in self.direct_sources if s.get("gov_kz")]
        if gov_sources:
            try:
                # ВАЖНО: Запуск в потоке
                gov_news = run_async_in_thread(self._scrape_all_gov_kz(gov_sources))
                all_news.extend(gov_news)
            except Exception as e:
                logger.error(f"Critical error scraping gov.kz: {e}")

        logger.info(f"Total news gathered: {len(all_news)}")
        return all_news

    async def _scrape_all_gov_kz(self, sources: List[Dict]) -> List[Dict]:
        global _gov_kz_tokens
        if _gov_kz_tokens is None:
            logger.info("🔑 Получаем токены gov.kz (в потоке)...")
            _gov_kz_tokens = await _fetch_gov_kz_tokens()

        if not _gov_kz_tokens:
            logger.error("Нет токенов gov.kz")
            return []

        all_news = []
        for source in sources:
            all_news.extend(self._scrape_gov_kz_source(source, _gov_kz_tokens))
        return all_news

    def _scrape_gov_kz_source(self, config: Dict, tokens: Dict) -> List[Dict]:
        """API запрос (синхронный requests)"""
        name = config.get("name", "Unknown")
        project = config.get("project")
        if not project: return []

        # URL запроса
        api_url = f"https://www.gov.kz/api/v1/public/content-manager/news?sort-by=created_date:DESC&projects=eq:{project}&page=1&size=10"
        headers = {
            "accept": "application/json", "accept-language": "ru",
            "user-agent": tokens.get("user-agent", "Mozilla/5.0"),
            "referer": f"https://www.gov.kz/memleket/entities/{project}/press/news?lang=ru",
            "hash": tokens["hash"], "token": tokens["token"],
        }
        
        news = []
        try:
            logger.info(f"API запрос: {name}...")
            resp = requests.get(api_url, headers=headers, timeout=15, verify=False)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # --- ИСПРАВЛЕНИЕ 1: Проверяем, список это или словарь ---
                if isinstance(data, list):
                    items = data
                else:
                    items = data.get("content", [])

                for item in items:
                    # --- ИСПРАВЛЕНИЕ 2: Ищем title ИЛИ name ---
                    title = item.get("title") or item.get("name")
                    if title:
                        title = title.strip()
                        
                    slug_id = item.get("id")
                    
                    if title and slug_id:
                        link = f"https://www.gov.kz/memleket/entities/{project}/press/news/details/{slug_id}?lang=ru"
                        
                        # Парсим дату API
                        raw_date = item.get("createdDate") or item.get("publishedDate")
                        pub_date = self._parse_date(str(raw_date)) if raw_date else datetime.now()

                        # Текст берем из функции (полный парсинг)
                        full_text, image, _ = self._fetch_full_text_and_image(link)
                        
                        news.append({
                            "title": title, "original_text": full_text or title,
                            "source_name": name, "source_url": link,
                            "image_url": image, "published_at": pub_date
                        })
        except Exception as e:
            logger.error(f"Error {name}: {e}")
        return news

    def _scrape_direct_source(self, config: Dict) -> List[Dict]:
        """Парсинг обычных HTML сайтов"""
        name = config.get("name", "Unknown")
        url = config.get("url")
        if not url: return []
        
        news = []
        try:
            logger.info(f"Direct scraping {name}...")
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            articles = soup.select(config.get("article_selector"))[:10]
            for art in articles:
                title_el = art.select_one(config.get("title_selector"))
                link_el = art.select_one(config.get("link_selector", "a"))
                
                if title_el:
                    title = title_el.get_text(strip=True)
                    href = link_el.get("href") if link_el else title_el.get("href")
                    if href:
                        base = config.get("base_url", "")
                        link = base + href if href.startswith("/") else href
                        
                        full_text, image, pub_date = self._fetch_full_text_and_image(link)
                        news.append({
                            "title": title, "original_text": full_text or title,
                            "source_name": name, "source_url": link,
                            "image_url": image, "published_at": pub_date
                        })
        except Exception as e:
            logger.error(f"Error {name}: {e}")
        return news

    def _fetch_full_text_and_image(self, url):
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
            if resp.status_code != 200: return None, None, None
            soup = BeautifulSoup(resp.content, "html.parser")
            paragraphs = soup.find_all("p")
            text = "\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text()) > 50])
            
            img = soup.find("meta", property="og:image")
            image_url = img.get("content") if img else None
            
            pub_date = self._extract_publish_date(soup)
            return text, image_url, pub_date
        except:
            return None, None, None

    def _extract_publish_date(self, soup):
        for prop in ("article:published_time", "published_time", "date"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                return self._parse_date(meta["content"])
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            return self._parse_date(time_el["datetime"])
        return datetime.now() 

    def _parse_date(self, value):
        if not value: return datetime.now()
        value = str(value).strip()[:25]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                if value.endswith("Z"): value = value[:-1] + "+00:00"
                d = datetime.fromisoformat(value.replace("Z", "+00:00")) if "+" in value else datetime.strptime(value[:10], "%Y-%m-%d")
                return d.astimezone(timezone.utc).replace(tzinfo=None)
            except: continue
        return datetime.now()

scraper = NewsScraper()

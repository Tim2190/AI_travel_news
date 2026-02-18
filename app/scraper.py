import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
import urllib3
import re
from typing import List, Dict, Optional, Tuple

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
    # --- ВЫСШЕЕ РУКОВОДСТВО (обычный BS4 парсинг, не SPA) ---
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

    # --- МИНИСТЕРСТВА (GOV.KZ - SPA, гибридный метод) ---
    {
        "name": "МинНацЭкономики",
        "url": "https://www.gov.kz/memleket/entities/economy/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "economy",
    },
    {
        "name": "МинФин",
        "url": "https://www.gov.kz/memleket/entities/minfin/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "minfin",
    },
    {
        "name": "МИД РК",
        "url": "https://www.gov.kz/memleket/entities/mfa/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "mfa",
    },
    {
        "name": "МВД РК",
        "url": "https://www.gov.kz/memleket/entities/qriim/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "qriim",
    },
    {
        "name": "МинТруда",
        "url": "https://www.gov.kz/memleket/entities/enbek/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "enbek",
    },
    {
        "name": "МинЗдрав",
        "url": "https://www.gov.kz/memleket/entities/dsm/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "dsm",
    },
    {
        "name": "МинПросвещения",
        "url": "https://www.gov.kz/memleket/entities/edu/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "edu",
    },
    {
        "name": "МинНауки",
        "url": "https://www.gov.kz/memleket/entities/sci/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "sci",
    },
    {
        "name": "МинПромСтрой",
        "url": "https://www.gov.kz/memleket/entities/mps/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "mps",
    },
    {
        "name": "МинТранспорт",
        "url": "https://www.gov.kz/memleket/entities/transport/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "transport",
    },
    {
        "name": "МинЦифры",
        "url": "https://www.gov.kz/memleket/entities/mdai/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "mdai",
    },
    {
        "name": "МинКультуры",
        "url": "https://www.gov.kz/memleket/entities/mam/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "mam",
    },
    {
        "name": "МинТуризм",
        "url": "https://www.gov.kz/memleket/entities/tsm/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "tsm",
    },
    {
        "name": "МинЭкологии",
        "url": "https://www.gov.kz/memleket/entities/ecogeo/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "ecogeo",
    },
    {
        "name": "МинСельХоз",
        "url": "https://www.gov.kz/memleket/entities/moa/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "moa",
    },
    {
        "name": "МинЭнерго",
        "url": "https://www.gov.kz/memleket/entities/energo/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "energo",
    },
    {
        "name": "МинЮст",
        "url": "https://www.gov.kz/memleket/entities/adilet/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "adilet",
    },
    {
        "name": "МЧС РК",
        "url": "https://www.gov.kz/memleket/entities/emer/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "emer",
    },
    {
        "name": "МинТорговли",
        "url": "https://www.gov.kz/memleket/entities/mti/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "mti",
    },

    # --- АКИМАТЫ МЕГАПОЛИСОВ ---
    {
        "name": "Акимат Алматы",
        "url": "https://www.gov.kz/memleket/entities/almaty/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "almaty",
    },
    {
        "name": "Акимат Астаны",
        "url": "https://www.gov.kz/memleket/entities/astana/press/news?lang=ru",
        "base_url": "https://www.gov.kz",
        "gov_kz": True,
        "project": "astana",
    },
]

# Кэш токенов — получаем один раз через Playwright, используем для всех gov.kz запросов
_gov_kz_tokens: Optional[Dict] = None


async def _fetch_gov_kz_tokens() -> Optional[Dict]:
    """
    Запускает Playwright ОДИН РАЗ, перехватывает hash+token,
    которые браузер передаёт в API gov.kz.
    Возвращает словарь с заголовками для requests.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright не установлен. Добавь в requirements.txt: playwright")
        return None

    tokens = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU",
            )
            page = await context.new_page()

            def handle_request(request):
                if "api/v1/public/content-manager/news" in request.url:
                    h = request.headers
                    if h.get("hash") and h.get("token"):
                        tokens["hash"] = h["hash"]
                        tokens["token"] = h["token"]
                        tokens["referer"] = h.get("referer", "https://www.gov.kz/")
                        tokens["user-agent"] = h.get("user-agent", "")
                        logger.info("✅ gov.kz токены получены через Playwright")

            page.on("request", handle_request)

            # Используем economy как «донора» токенов — они работают для всех проектов
            await page.goto(
                "https://www.gov.kz/memleket/entities/economy/press/news?lang=ru",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_selector(
                "a[href*='/press/news/details/']",
                timeout=30000,
            )
            await browser.close()

    except Exception as e:
        logger.error(f"Ошибка получения токенов gov.kz: {e}")
        return None

    return tokens if tokens else None


class NewsScraper:
    def __init__(self, direct_sources: List[Dict] = None):
        self.direct_sources = direct_sources or DIRECT_SCRAPE_SOURCES

    # ========== ИСПРАВЛЕНИЕ ПРОБЛЕМЫ 1: async/await вместо loop.run_until_complete ==========
    async def scrape_async(self) -> List[Dict]:
        """
        Async-версия scrape() для интеграции с FastAPI.
        Вызывай её из FastAPI так: await scraper.scrape_async()
        """
        all_news = []

        # Разделяем источники на gov.kz и обычные
        gov_sources = [s for s in self.direct_sources if s.get("gov_kz")]
        regular_sources = [s for s in self.direct_sources if not s.get("gov_kz")]

        # Обычные источники — синхронный BS4 (в отдельном потоке чтобы не блокировать)
        import asyncio
        loop = asyncio.get_event_loop()
        regular_news = await loop.run_in_executor(
            None,
            self._scrape_all_regular_sources,
            regular_sources
        )
        all_news.extend(regular_news)

        # gov.kz источники — async гибридный метод
        if gov_sources:
            gov_news = await self._scrape_all_gov_kz(gov_sources)
            all_news.extend(gov_news)

        logger.info(f"Total news gathered: {len(all_news)}")
        return all_news

    def _scrape_all_regular_sources(self, sources: List[Dict]) -> List[Dict]:
        """Синхронная обработка обычных источников (не gov.kz)"""
        all_news = []
        for source in sources:
            all_news.extend(self._scrape_direct_source(source))
        return all_news

    async def _scrape_all_gov_kz(self, sources: List[Dict]) -> List[Dict]:
        """
        Получает токены ОДИН РАЗ через Playwright,
        затем обходит все gov.kz источники через лёгкий requests.
        """
        global _gov_kz_tokens

        if _gov_kz_tokens is None:
            logger.info("🔑 Получаем токены gov.kz через Playwright...")
            _gov_kz_tokens = await _fetch_gov_kz_tokens()

        if not _gov_kz_tokens:
            logger.error("Не удалось получить токены gov.kz — пропускаем все gov.kz источники")
            return []

        all_news = []
        for source in sources:
            all_news.extend(self._scrape_gov_kz_source(source, _gov_kz_tokens))

        return all_news

    def _scrape_gov_kz_source(self, config: Dict, tokens: Dict) -> List[Dict]:
        """
        Парсит один gov.kz источник через прямой API запрос с токенами.
        Браузер здесь не нужен — только лёгкий requests.
        """
        name = config.get("name", "Unknown")
        project = config.get("project")
        base_url = config.get("base_url", "https://www.gov.kz")

        if not project:
            logger.warning(f"'{name}' пропущен: не указан 'project'")
            return []

        api_url = (
            f"https://www.gov.kz/api/v1/public/content-manager/news"
            f"?sort-by=created_date:DESC&projects=eq:{project}&page=1&size=20"
        )

        headers = {
            "accept": "application/json",
            "accept-language": "ru",
            "user-agent": tokens.get("user-agent", "Mozilla/5.0"),
            "referer": f"{base_url}/memleket/entities/{project}/press/news?lang=ru",
            "hash": tokens["hash"],
            "token": tokens["token"],
        }

        news = []
        try:
            logger.info(f"API запрос: {name}...")
            resp = requests.get(api_url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
            data = resp.json()

            # API возвращает {"content": [...], "totalElements": N, ...}
            items = data.get("content", [])

            for item in items:
                title = item.get("name", "").strip()
                slug = item.get("id") or item.get("slug", "")
                if not title or not slug:
                    continue

                link = f"{base_url}/memleket/entities/{project}/press/news/details/{slug}?lang=ru"

                # Дата из API — уже есть, не нужно парсить HTML
                published_at = None
                raw_date = item.get("createdDate") or item.get("created_date") or item.get("publishedDate")
                if raw_date:
                    published_at = self._parse_date(str(raw_date))

                # Полный текст и картинку берём со страницы статьи
                full_text, image_url, page_date = self._fetch_full_text_and_image(link)

                # ВАЖНО: если дата из API пустая, используем дату из страницы
                final_date = published_at or page_date

                news.append({
                    "title": title,
                    "original_text": full_text or title,
                    "source_name": name,
                    "source_url": link,
                    "image_url": image_url,
                    "published_at": final_date,
                })

        except Exception as e:
            logger.error(f"Ошибка API {name}: {e}")

        return news

    def _scrape_direct_source(self, config: Dict) -> List[Dict]:
        """Парсит страницу со списком статей по селекторам (старый метод для не-SPA)."""
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
            resp = requests.get(url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.content, "html.parser")
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

    # ========== ИСПРАВЛЕНИЕ ПРОБЛЕМЫ 2: Улучшенный парсинг дат ==========
    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """
        Извлекает дату публикации из:
        1. Мета-тегов (og:published_time и т.д.)
        2. <time datetime="">
        3. Видимого текста страницы (регулярные выражения)
        """
        # 1. Пробуем мета-теги
        for prop in ("article:published_time", "published_time", "date", "og:updated_time"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                parsed = self._parse_date(meta["content"])
                if parsed:
                    return parsed

        # 2. Пробуем <time datetime="">
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            parsed = self._parse_date(time_el["datetime"])
            if parsed:
                return parsed

        # 3. Ищем дату в видимом тексте страницы через regex
        # Паттерны: "18 февраля 2025", "18.02.2025", "2025-02-18"
        text = soup.get_text()
        date_from_text = self._extract_date_from_text(text)
        if date_from_text:
            return date_from_text

        return None

    def _extract_date_from_text(self, text: str) -> Optional[datetime]:
        """
        Ищет дату в тексте через регулярные выражения.
        Поддерживает форматы:
        - "18 февраля 2025"
        - "18.02.2025"
        - "2025-02-18"
        """
        # Месяцы на русском
        months_ru = {
            "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
            "мая": 5, "июня": 6, "июля": 7, "августа": 8,
            "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
        }

        # 1. Формат "18 февраля 2025"
        pattern1 = r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})"
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month = months_ru[match.group(2).lower()]
            year = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        # 2. Формат "18.02.2025" или "18/02/2025"
        pattern2 = r"(\d{1,2})[./](\d{1,2})[./](\d{4})"
        match = re.search(pattern2, text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        # 3. Формат ISO "2025-02-18"
        pattern3 = r"(\d{4})-(\d{1,2})-(\d{1,2})"
        match = re.search(pattern3, text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

        return None

    def _parse_date(self, value: str) -> Optional[datetime]:
        """Парсит ISO дату из строки."""
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
            except Exception:
                continue
        return None

    def _fetch_full_text_and_image(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=15, verify=False)
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

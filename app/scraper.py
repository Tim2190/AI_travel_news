import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import logging
import urllib3
import re
import time
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
                        tokens["sec-fetch-dest"] = h.get("sec-fetch-dest", "empty")
                        tokens["sec-fetch-mode"] = h.get("sec-fetch-mode", "cors")
                        tokens["sec-fetch-site"] = h.get("sec-fetch-site", "same-origin")
                        tokens["obtained_at"] = time.time()  # запоминаем время получения
                        logger.info("✅ gov.kz токены получены через Playwright")

            page.on("request", handle_request)

            await page.goto(
                "https://www.gov.kz/memleket/entities/economy/press/news?lang=ru",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            
            await page.wait_for_selector(
                "a[href*='/press/news/details/']",
                timeout=45000,
            )
            await browser.close()

    except Exception as e:
        logger.error(f"Ошибка получения токенов gov.kz: {e}")
        return None

    return tokens if tokens else None


class NewsScraper:
    def __init__(self, direct_sources: List[Dict] = None):
        self.direct_sources = direct_sources or DIRECT_SCRAPE_SOURCES

    # ========== ASYNC МЕТОД ДЛЯ ИНТЕГРАЦИИ С FASTAPI ==========
    async def scrape_async(self) -> List[Dict]:
        """
        Async-версия scrape() для интеграции с FastAPI.
        Вызывай её из FastAPI так: await scraper.scrape_async()
        """
        all_news = []

        # Только gov.kz источники (Akorda и PrimeMinister убрали)
        gov_sources = [s for s in self.direct_sources if s.get("gov_kz")]

        # gov.kz источники — async гибридный метод с батчами
        if gov_sources:
            gov_news = await self._scrape_all_gov_kz_batched(gov_sources)
            all_news.extend(gov_news)

        logger.info(f"Total news gathered: {len(all_news)}")
        return all_news

    async def _scrape_all_gov_kz_batched(self, sources: List[Dict]) -> List[Dict]:
        """
        Обрабатывает gov.kz источники батчами по 5 штук.
        Для каждого батча получаются СВЕЖИЕ токены через Playwright.
        Это защита от протухания токенов и rate limiting.
        """
        all_news = []
        batch_size = 5
        
        total_batches = (len(sources) + batch_size - 1) // batch_size
        logger.info(f"📦 Всего источников: {len(sources)}, разбиваем на {total_batches} батчей по {batch_size}")

        for batch_idx in range(0, len(sources), batch_size):
            batch = sources[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            
            logger.info(f"🔄 Батч {batch_num}/{total_batches}: {[s['name'] for s in batch]}")
            
            # Получаем свежие токены для каждого батча
            try:
                tokens = await _fetch_gov_kz_tokens()
                if not tokens:
                    logger.error(f"❌ Батч {batch_num}: не удалось получить токены, пропускаем")
                    continue
                
                age = time.time() - tokens.get('obtained_at', 0)
                logger.info(f"🔑 Батч {batch_num}: токены свежие ({age:.1f} сек)")
                
            except Exception as e:
                logger.error(f"❌ Батч {batch_num}: ошибка получения токенов: {e}")
                continue

            # Обрабатываем источники в батче
            for source in batch:
                try:
                    news = self._scrape_gov_kz_source(source, tokens)
                    all_news.extend(news)
                    # Задержка между источниками
                    time.sleep(0.7)
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки {source['name']}: {e}")
                    continue

            # Пауза между батчами (чтобы не палиться перед сервером)
            if batch_num < total_batches:
                logger.info(f"⏸️  Пауза 3 сек перед следующим батчем...")
                time.sleep(3)

        logger.info(f"✅ Все батчи обработаны. Собрано новостей: {len(all_news)}")
        return all_news

    def _scrape_gov_kz_source(self, config: Dict, tokens: Dict) -> List[Dict]:
        """
        Парсит один gov.kz источник через прямой API запрос с токенами.
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
            "user-agent": tokens.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            "referer": f"{base_url}/memleket/entities/{project}/press/news?lang=ru",
            "hash": tokens["hash"],
            "token": tokens["token"],
            "sec-fetch-dest": tokens.get("sec-fetch-dest", "empty"),
            "sec-fetch-mode": tokens.get("sec-fetch-mode", "cors"),
            "sec-fetch-site": tokens.get("sec-fetch-site", "same-origin"),
            "origin": base_url,
        }

        news = []
        try:
            logger.info(f"API запрос: {name}...")
            resp = requests.get(api_url, headers=headers, timeout=15, verify=False)
            
            if resp.status_code != 200:
                logger.error(f"API {name} вернул код {resp.status_code}")
                logger.error(f"Ответ сервера: {resp.text[:500]}")
                return []
            
            data = resp.json()

            # Обработка разных форматов ответа
            items = []
            if isinstance(data, list):
                items = data
                logger.info(f"{name}: API вернул список из {len(items)} элементов")
            elif isinstance(data, dict):
                items = data.get("content", [])
                if not items:
                    items = data.get("data", []) or data.get("items", []) or data.get("news", [])
            else:
                logger.error(f"{name}: Unexpected API response type: {type(data)}")
                return []

            if not items:
                logger.warning(f"{name}: API вернул пустой список новостей")
                return []

            logger.info(f"{name}: Обрабатываем {len(items)} новостей")

            for item in items:
                if not isinstance(item, dict):
                    continue

                title = item.get("name", "").strip() or item.get("title", "").strip()
                slug = item.get("id") or item.get("slug", "")
                
                if not title or not slug:
                    continue

                link = f"{base_url}/memleket/entities/{project}/press/news/details/{slug}?lang=ru"

                # Дата из API
                published_at = None
                raw_date = item.get("createdDate") or item.get("created_date") or item.get("publishedDate") or item.get("date")
                if raw_date:
                    published_at = self._parse_date(str(raw_date))

                # КРИТИЧЕСКОЕ ЛОГИРОВАНИЕ ДАТ
                if published_at:
                    logger.info(f"  📅 [{title[:40]}...] → Дата из API: {published_at.strftime('%Y-%m-%d %H:%M')}")
                else:
                    logger.warning(f"  ⚠️ [{title[:40]}...] → Дата в API отсутствует, парсим страницу...")

                # Полный текст и картинку берём со страницы статьи
                full_text, image_url, page_date = self._fetch_full_text_and_image(link)

                # ВАЖНО: если дата из API пустая, используем дату из страницы
                final_date = published_at or page_date

                if final_date:
                    days_old = (datetime.now() - final_date).days
                    logger.info(f"  ✅ ФИНАЛЬНАЯ ДАТА: {final_date.strftime('%Y-%m-%d %H:%M')} (возраст: {days_old} дней)")
                else:
                    logger.error(f"  ❌ [{title[:40]}...] → ДАТА НЕ НАЙДЕНА НИГДЕ!")

                news.append({
                    "title": title,
                    "original_text": full_text or title,
                    "source_name": name,
                    "source_url": link,
                    "image_url": image_url,
                    "published_at": final_date,
                })

            logger.info(f"✅ {name}: собрано {len(news)} новостей")

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети API {name}: {e}")
        except Exception as e:
            logger.error(f"Ошибка API {name}: {e}", exc_info=True)

        return news

    # ========== УЛУЧШЕННЫЙ ПАРСИНГ ДАТ ==========
    def _extract_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Извлекает дату публикации из мета-тегов, <time> и текста"""
        # 1. Мета-теги
        for prop in ("article:published_time", "published_time", "date", "og:updated_time"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                parsed = self._parse_date(meta["content"])
                if parsed:
                    return parsed

        # 2. <time datetime="">
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el and time_el.get("datetime"):
            parsed = self._parse_date(time_el["datetime"])
            if parsed:
                return parsed

        # 3. Текст страницы
        text = soup.get_text()
        date_from_text = self._extract_date_from_text(text)
        if date_from_text:
            return date_from_text

        return None

    def _extract_date_from_text(self, text: str) -> Optional[datetime]:
        """Ищет дату в тексте через regex"""
        months_ru = {
            "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
            "мая": 5, "июня": 6, "июля": 7, "августа": 8,
            "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
        }

        # 1. "18 февраля 2025"
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

        # 2. "18.02.2025"
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

        # 3. ISO "2025-02-18"
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
        """Парсит ISO дату из строки"""
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

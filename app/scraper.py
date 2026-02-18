import logging
import requests
import re
import urllib3
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from .config import settings

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Словари для парсинга текстовых дат
MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12
}

MONTHS_KZ = {
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
    "қаң": 1, "ақп": 2, "нау": 3, "сәу": 4, "мам": 5, "мау": 6,
    "шіл": 7, "там": 8, "қыр": 9, "қаз": 10, "қар": 11, "жел": 12
}

# 1. Прямые источники (Akorda, PrimeMinister)
DIRECT_SOURCES = [
    {
        "name": "Akorda (Президент)",
        "url": "https://www.akorda.kz/ru/events",
        "base_url": "https://www.akorda.kz",
        # Ищем ЛЮБЫЕ ссылки, содержащие /events/ в адресе (это надежнее классов)
        "link_pattern": re.compile(r"/ru/events/[\w-]+"), 
        "container_tag": "div" # Ограничитель поиска (ищем внутри div)
    },
    {
        "name": "PrimeMinister (Правительство)",
        "url": "https://primeminister.kz/ru/news",
        "base_url": "https://primeminister.kz",
        # Ищем ЛЮБЫЕ ссылки на новости
        "link_pattern": re.compile(r"/ru/news/[\w-]+"),
        "container_tag": "div"
    }
]

# 2. GOV.KZ (API ID)
GOV_KZ_PROJECTS = {
    "МинНацЭкономики": 4, "МинФин": 2, "МИД РК": 6, "МВД РК": 11,
    "МинТруда": 21, "МинЗдрав": 17, "МинПросвещения": 14, "МинНауки": 15,
    "МинПромСтрой": 3, "МинТранспорт": 22, "МинЦифры": 8, "МинКультуры": 19,
    "МинТуризм": 24, "МинЭкологии": 16, "МинСельХоз": 18, "МинЭнерго": 20,
    "МинЮст": 9, "МЧС РК": 5, "МинТорговли": 23, "Акимат Алматы": 118, "Акимат Астаны": 105
}

class Scraper:
    def __init__(self):
        self.session = requests.Session()
        # УПРОЩЕННЫЕ ЗАГОЛОВКИ (чтобы не пугать сервер 500-й ошибкой)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Парсер даты."""
        if not date_str: return None
        date_str = str(date_str).strip().lower()

        try:
            iso_clean = date_str.split("+")[0].split(".")[0].replace("z", "")
            if "t" in iso_clean: return datetime.fromisoformat(iso_clean)
            if len(iso_clean) == 10 and "-" in iso_clean: return datetime.strptime(iso_clean, "%Y-%m-%d")
        except: pass

        clean_text = re.sub(r"\s+\d{1,2}:\d{2}.*", "", date_str) 
        clean_text = re.sub(r"[^\w\s\.]", "", clean_text)
        
        if "." in clean_text:
            try: return datetime.strptime(clean_text, "%d.%m.%Y")
            except: pass

        parts = clean_text.split()
        if len(parts) >= 2:
            try:
                day = int(re.sub(r"\D", "", parts[0]))
                month_str = parts[1]
                month = MONTHS_RU.get(month_str) or MONTHS_KZ.get(month_str)
                year = datetime.now().year
                if len(parts) > 2 and parts[2].isdigit():
                    year = int(parts[2])
                    if 2020 < year < 2030: year = year
                if month: return datetime(year, month, day)
            except: pass
        return None

    def find_date_in_text(self, text: str) -> Optional[datetime]:
        """Ищет дату в начале текста."""
        if not text: return None
        head = text[:600]
        
        match_dots = re.search(r"\d{2}\.\d{2}\.\d{4}", head)
        if match_dots: return self.parse_date(match_dots.group(0))

        match_text = re.search(r"\d{1,2}\s+[а-яА-Яәіңғүұқөһ]{3,}\s+\d{4}", head)
        if match_text: return self.parse_date(match_text.group(0))
        return None

    def scrape(self) -> List[Dict]:
        """Главный метод запуска."""
        logger.warning("🏁 STARTING SCRAPE CYCLE (SIMPLE MODE)...")
        all_news = []
        all_news.extend(self.scrape_gov_kz_api())
        for source in DIRECT_SOURCES:
            all_news.extend(self.scrape_direct(source))
        logger.warning(f"✅ CYCLE FINISHED. Total items found: {len(all_news)}")
        return all_news

    def scrape_gov_kz_api(self) -> List[Dict]:
        results = []
        base_api = "https://gov.kz/api/v1/public/news"
        
        for name, project_id in GOV_KZ_PROJECTS.items():
            try:
                params = {"projects": project_id, "lang": "ru", "limit": 3}
                # Таймаут 10 сек, простые заголовки
                resp = self.session.get(base_api, params=params, timeout=10, verify=False)
                
                if resp.status_code == 200:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("content", [])
                    
                    for item in items:
                        title = item.get("title")
                        if not title: continue

                        pub_date = self.parse_date(item.get("publish_date") or item.get("created_date"))
                        body = item.get("body") or ""
                        soup = BeautifulSoup(body, "html.parser")
                        text = soup.get_text(separator="\n").strip()

                        if not pub_date: pub_date = self.find_date_in_text(text)
                        # FALLBACK: Если даты нет — ставим СЕЙЧАС
                        if not pub_date: pub_date = datetime.now()

                        news_id = item.get("id")
                        proj_id_from_api = item.get("projects", [project_id])[0]
                        link = f"https://gov.kz/memleket/entities/{proj_id_from_api}/press/news/details/{news_id}?lang=ru"
                        
                        img = None
                        if item.get("visual_content"):
                             img = item["visual_content"][0].get("source")

                        results.append({
                            "title": title, "original_text": text[:4000],
                            "source_name": name, "source_url": link,
                            "published_at": pub_date, "image_url": img
                        })
                    if items: logger.info(f"API {name}: found {len(items)}")
                else:
                    logger.warning(f"API {name} Error: Status {resp.status_code}")
            except Exception as e:
                logger.error(f"API {name} Exception: {e}")
        return results

    def scrape_direct(self, config: Dict) -> List[Dict]:
        results = []
        name = config["name"]
        try:
            resp = self.session.get(config["url"], timeout=20, verify=False)
            if resp.status_code != 200: 
                logger.warning(f"Direct {name}: Status {resp.status_code}")
                return []
            
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # НОВАЯ ЛОГИКА: Ищем все ссылки <a>, которые подходят под паттерн
            # Это игнорирует классы и ищет просто по структуре URL
            seen_links = set()
            found_links = []
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Если ссылка подходит под паттерн (например /ru/events/...)
                if config["link_pattern"].search(href):
                    full_link = config["base_url"] + href if href.startswith("/") else href
                    if full_link not in seen_links:
                        seen_links.add(full_link)
                        found_links.append((a, full_link))
                        if len(found_links) >= 3: break # Берем только 3 свежих

            if not found_links:
                logger.warning(f"Direct {name}: No matching links found")

            for link_el, full_link in found_links:
                title = link_el.get_text(strip=True)
                if len(title) < 5: continue # Пропускаем мусор

                full_text, image, pub_date = self.fetch_details(full_link)
                
                if not pub_date: pub_date = datetime.now()
                
                results.append({
                    "title": title, "original_text": full_text or title,
                    "source_name": name, "source_url": full_link,
                    "published_at": pub_date, "image_url": image
                })
            
            if results: logger.info(f"Direct {name}: found {len(results)}")
        except Exception as e:
            logger.error(f"Direct {name} Error: {e}")
        return results

    def fetch_details(self, url: str):
        try:
            resp = self.session.get(url, timeout=10, verify=False)
            soup = BeautifulSoup(resp.content, "html.parser")
            text = soup.get_text(separator="\n").strip()
            
            img = None
            meta_img = soup.find("meta", property="og:image")
            if meta_img: img = meta_img.get("content")

            pub_date = None
            for prop in ["article:published_time", "published_time", "date"]:
                meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
                if meta:
                    pub_date = self.parse_date(meta.get("content"))
                    if pub_date: break
            
            if not pub_date: pub_date = self.find_date_in_text(text)

            return text, img, pub_date
        except:
            return None, None, None

scraper = Scraper()

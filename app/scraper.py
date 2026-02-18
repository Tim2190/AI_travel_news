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

# Обновленные селекторы и User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
}

DIRECT_SOURCES = [
    {
        "name": "Akorda (Президент)",
        "url": "https://www.akorda.kz/ru/events",
        # Ищем любой блок, похожий на новость
        "article_selector": ".event-item, .news-list__item, div.item, .news-item", 
        "title_selector": "h3, h4, .title",
        "link_selector": "a", # Любая ссылка внутри блока
        "base_url": "https://www.akorda.kz"
    },
    {
        "name": "PrimeMinister (Правительство)",
        "url": "https://primeminister.kz/ru/news",
        "article_selector": ".news_item, .card, .post-item, .news-list-item",
        "title_selector": ".news_title, .card-title, h3",
        "link_selector": "a",
        "base_url": "https://primeminister.kz"
    }
]

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
        self.session.headers.update(HEADERS)

    def parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str: return None
        date_str = str(date_str).strip().lower()

        # ISO
        try:
            iso_clean = date_str.split("+")[0].split(".")[0].replace("z", "")
            if "t" in iso_clean: return datetime.fromisoformat(iso_clean)
            if len(iso_clean) == 10 and "-" in iso_clean: return datetime.strptime(iso_clean, "%Y-%m-%d")
        except: pass

        # Text
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
        if not text: return None
        head = text[:500]
        
        match_dots = re.search(r"\d{2}\.\d{2}\.\d{4}", head)
        if match_dots: return self.parse_date(match_dots.group(0))

        match_text = re.search(r"\d{1,2}\s+[а-яА-Яәіңғүұқөһ]{3,}\s+\d{4}", head)
        if match_text: return self.parse_date(match_text.group(0))
        return None

    def scrape(self) -> List[Dict]:
        logger.info("🔍 START SCRAPING...")
        all_news = []
        all_news.extend(self.scrape_gov_kz_api())
        for source in DIRECT_SOURCES:
            all_news.extend(self.scrape_direct(source))
        
        logger.info(f"✅ SCRAPE FINISHED. Found: {len(all_news)}")
        return all_news

    def scrape_gov_kz_api(self) -> List[Dict]:
        results = []
        base_api = "https://gov.kz/api/v1/public/news"
        
        for name, project_id in GOV_KZ_PROJECTS.items():
            try:
                params = {"projects": project_id, "lang": "ru", "limit": 3}
                # Добавил таймаут побольше
                resp = self.session.get(base_api, params=params, timeout=15, verify=False)
                
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
                    # Убрал спам "API OK", теперь только если реально нашли
                    if items: logger.info(f"API {name}: found {len(items)}")
                else:
                    # ВАЖНО: Логируем код ошибки
                    logger.warning(f"API {name} Failed: Status {resp.status_code}")
            except Exception as e:
                logger.error(f"API {name} Error: {e}")
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
            items = soup.select(config["article_selector"])[:3]
            
            if not items:
                logger.warning(f"Direct {name}: No items found (check selectors)")

            for item in items:
                # Ищем любую ссылку в блоке
                link_el = item.select_one(config["link_selector"])
                if not link_el: continue
                
                href = link_el.get("href")
                if not href: continue
                full_link = config["base_url"] + href if href.startswith("/") else href
                
                # Заголовок - либо из тега заголовка, либо текст ссылки
                title_el = item.select_one(config["title_selector"])
                title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)

                full_text, image, pub_date = self.fetch_details(full_link)
                
                if not pub_date:
                    date_el = item.find(string=re.compile(r"\d{1,2}\s+[а-яА-Я]{3,}\s+\d{4}"))
                    if date_el: pub_date = self.parse_date(date_el)
                
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

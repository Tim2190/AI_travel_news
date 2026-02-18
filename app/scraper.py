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

# 1. Прямые источники (Akorda, PrimeMinister) - парсим HTML
DIRECT_SOURCES = [
    {
        "name": "Akorda (Президент)",
        "url": "https://www.akorda.kz/ru/events",
        "article_selector": ".event-item, .news-list__item, div.item",
        "title_selector": "h3 a, .title a, a",
        "link_selector": "h3 a, .title a, a",
        "base_url": "https://www.akorda.kz"
    },
    {
        "name": "PrimeMinister (Правительство)",
        "url": "https://primeminister.kz/ru/news",
        "article_selector": ".news_item, .card, .post-item",
        "title_selector": ".news_title a, .card-title a, a",
        "link_selector": "a",
        "base_url": "https://primeminister.kz"
    }
]

# 2. GOV.KZ (Все министерства и акиматы) - используем API ID
# Я перевел все твои ссылки в ID проектов. Это ВСЕ твои источники.
GOV_KZ_PROJECTS = {
    "МинНацЭкономики": 4,
    "МинФин": 2,
    "МИД РК": 6,
    "МВД РК": 11,
    "МинТруда": 21,
    "МинЗдрав": 17,
    "МинПросвещения": 14,
    "МинНауки": 15,
    "МинПромСтрой": 3,
    "МинТранспорт": 22,
    "МинЦифры": 8,
    "МинКультуры": 19,
    "МинТуризм": 24,
    "МинЭкологии": 16,
    "МинСельХоз": 18,
    "МинЭнерго": 20,
    "МинЮст": 9,
    "МЧС РК": 5,
    "МинТорговли": 23,
    "Акимат Алматы": 118,
    "Акимат Астаны": 105
}

class Scraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*"
        })

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Универсальный парсер даты (ISO + Текст)."""
        if not date_str:
            return None
        
        date_str = str(date_str).strip().lower()

        # 1. Попытка распарсить ISO (из API Gov.kz)
        try:
            iso_clean = date_str.split("+")[0].split(".")[0].replace("z", "")
            if "t" in iso_clean:
                return datetime.fromisoformat(iso_clean)
            if len(iso_clean) == 10 and "-" in iso_clean:
                return datetime.strptime(iso_clean, "%Y-%m-%d")
        except: pass

        # 2. Попытка распарсить текстовую дату (из HTML)
        clean_text = re.sub(r"\s+\d{1,2}:\d{2}.*", "", date_str) 
        clean_text = re.sub(r"[^\w\s]", "", clean_text)
        
        parts = clean_text.split()
        if len(parts) >= 2:
            try:
                day = int(re.sub(r"\D", "", parts[0]))
                month_str = parts[1]
                year = datetime.now().year 
                
                if len(parts) > 2 and parts[2].isdigit():
                    possible_year = int(parts[2])
                    if 2020 < possible_year < 2030:
                        year = possible_year

                month = MONTHS_RU.get(month_str) or MONTHS_KZ.get(month_str)
                if month:
                    return datetime(year, month, day)
            except: pass
            
        return None

    def scrape(self) -> List[Dict]:
        """Главный метод запуска."""
        all_news = []
        
        # 1. Сбор через API (Gov.kz) - быстро и надежно
        all_news.extend(self.scrape_gov_kz_api())

        # 2. Сбор через HTML (Akorda, PM)
        for source in DIRECT_SOURCES:
            all_news.extend(self.scrape_direct(source))

        return all_news

    def scrape_gov_kz_api(self) -> List[Dict]:
        """Сбор новостей через официальное API Gov.kz"""
        results = []
        base_api = "https://gov.kz/api/v1/public/news"
        
        for name, project_id in GOV_KZ_PROJECTS.items():
            try:
                # Запрашиваем 5 последних новостей
                params = {"projects": project_id, "lang": "ru", "limit": 5}
                resp = self.session.get(base_api, params=params, timeout=10, verify=False)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Иногда API отдает список, иногда объект с полем content
                    items = data if isinstance(data, list) else data.get("content", [])
                    
                    for item in items:
                        title = item.get("title")
                        if not title: continue

                        # ДАТА (Берем из API, она там точная)
                        pub_date = self.parse_date(item.get("publish_date") or item.get("created_date"))
                        if not pub_date: continue 

                        # ТЕКСТ (Чистим HTML)
                        body = item.get("body") or ""
                        soup = BeautifulSoup(body, "html.parser")
                        text = soup.get_text(separator="\n").strip()

                        # ССЫЛКА (Генерируем правильную ссылку на сайт)
                        news_id = item.get("id")
                        # projects возвращает список [4], берем первый элемент
                        proj_id_from_api = item.get("projects", [project_id])[0]
                        link = f"https://gov.kz/memleket/entities/{proj_id_from_api}/press/news/details/{news_id}?lang=ru"
                        
                        # КАРТИНКА
                        img = None
                        if item.get("visual_content"):
                             img = item["visual_content"][0].get("source")

                        results.append({
                            "title": title,
                            "original_text": text[:4000],
                            "source_name": name,
                            "source_url": link,
                            "published_at": pub_date,
                            "image_url": img
                        })
                logger.info(f"API {name}: OK")
            except Exception as e:
                logger.error(f"API {name} Error: {e}")
                
        return results

    def scrape_direct(self, config: Dict) -> List[Dict]:
        """Парсинг HTML для Akorda и PM (где нет открытого API)"""
        results = []
        name = config["name"]
        
        try:
            resp = self.session.get(config["url"], timeout=20, verify=False)
            if resp.status_code != 200: return []
            
            soup = BeautifulSoup(resp.content, "html.parser")
            items = soup.select(config["article_selector"])[:5]
            
            for item in items:
                link_el = item.select_one(config["link_selector"])
                if not link_el: continue
                
                href = link_el.get("href")
                if not href: continue
                
                full_link = config["base_url"] + href if href.startswith("/") else href
                title = link_el.get_text(strip=True)

                # Заходим внутрь за датой
                full_text, image, pub_date = self.fetch_details(full_link)
                
                # Если внутри даты нет, ищем снаружи
                if not pub_date:
                    date_el = item.find(string=re.compile(r"\d{1,2}\s+[а-яА-Я]{3,}\s+\d{4}"))
                    if date_el:
                        pub_date = self.parse_date(date_el)
                
                if pub_date:
                    results.append({
                        "title": title,
                        "original_text": full_text or title,
                        "source_name": name,
                        "source_url": full_link,
                        "published_at": pub_date,
                        "image_url": image
                    })

            logger.info(f"Direct {name}: {len(results)} items")
        except Exception as e:
            logger.error(f"Direct {name} Error: {e}")
            
        return results

    def fetch_details(self, url: str):
        """Загружает страницу новости и ищет детали."""
        try:
            resp = self.session.get(url, timeout=10, verify=False)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            text = "\n".join([p.get_text(strip=True) for p in soup.find_all("p")])
            
            img = None
            meta_img = soup.find("meta", property="og:image")
            if meta_img: img = meta_img.get("content")

            pub_date = None
            # Мета-теги
            for prop in ["article:published_time", "published_time", "date"]:
                meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
                if meta:
                    pub_date = self.parse_date(meta.get("content"))
                    if pub_date: break
            
            # Текст (18 февраля 2026)
            if not pub_date:
                date_pattern = re.compile(r"\d{1,2}\s+[а-яА-Яәіңғүұқөһ]{3,}\s+\d{4}")
                date_text = soup.find(string=date_pattern)
                if date_text:
                    pub_date = self.parse_date(date_text)

            return text, img, pub_date
        except:
            return None, None, None

scraper = Scraper()

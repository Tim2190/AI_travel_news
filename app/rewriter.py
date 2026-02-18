import logging
import re
import asyncio
import google.generativeai as genai
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ МОДЕЛЕЙ ---
MODEL_KZ = "gemini-2.0-flash"       
MODEL_RU_JOURNALIST = "gemini-1.5-flash"
MODEL_RU_EDITOR = "gemini-2.0-flash"

class GeminiRewriter:
    def __init__(self):
        # Инициализация стандартной библиотеки
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        else:
            logger.error("CRITICAL: GEMINI_API_KEY is missing in settings!")

    def _is_kazakh(self, text: str) -> bool:
        """Определяет, является ли текст казахским по специфическим буквам."""
        # Ищем уникальные казахские буквы
        kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
        return bool(re.search(kz_chars, text, re.IGNORECASE))

    async def rewrite(self, text: str) -> str:
        """Маршрутизатор: выбирает цепочку обработки в зависимости от языка."""
        if not text:
            return ""

        if self._is_kazakh(text):
            return await self._process_kz(text)
        else:
            return await self._process_ru_pipeline(text)

    # =================================================================
    # ВЕТКА 1: КАЗАХСКИЙ ЯЗЫК (Gemini 2.0 Flash)
    # =================================================================
    async def _process_kz(self, text: str) -> str:
        logger.info(f"🇰🇿 KZ Pipeline: Working with {MODEL_KZ}")
        
        system_prompt = (
            "Сен — кәсіби редакторсың. Мәтінді қазақ тілінде өңде.\n"
            "ЕРЕЖЕЛЕР:\n"
            "1. Ешқандай кіріспе сөз жазба ('Міне, мәтін...', 'Мен өзгерттім...').\n"
            "2. Орысша сөздерді (русизмдерді) қолданба.\n"
            "3. Ресми, бірақ түсінікті тілмен жаз.\n"
            "4. Атау септігіндегі ай аттарын дұрыс қолдан: қаңтар, ақпан, наурыз, сәуір, мамыр, маусым, шілде, тамыз, қыркүйек, қазан, қараша, желтоқсан.\n"
            "5. ТЕК ҚАНА МӘТІНДІ ҚАЙТАР.\n\n"
            "ҚҰРЫЛЫМ:\n"
            "<b>Тақырып</b>\n"
            "(бос жол)\n"
            "Негізгі мәтін (2-3 абзац).\n"
            "#хэштегтер"
        )

        try:
            # Инициализируем модель под конкретную задачу
            model = genai.GenerativeModel(
                model_name=MODEL_KZ,
                system_instruction=system_prompt
            )
            
            # Запускаем в отдельном потоке, чтобы не блокировать бота
            response = await asyncio.to_thread(
                model.generate_content,
                text,
                generation_config=genai.GenerationConfig(temperature=0.3)
            )
            return self._clean_output(response.text)
        except Exception as e:
            logger.error(f"KZ Pipeline Error: {e}")
            return text # Возвращаем оригинал, если модель упала

    # =================================================================
    # ВЕТКА 2: РУССКИЙ ЯЗЫК (1.5 Flash -> 2.0 Flash)
    # =================================================================
    async def _process_ru_pipeline(self, text: str) -> str:
        logger.info("🇷🇺 RU Pipeline Started...")

        # ШАГ 1: ЖУРНАЛИСТ (Gemini 1.5 Flash) - Сбор фактуры
        logger.info(f"--- Step 1: Journalist ({MODEL_RU_JOURNALIST})")
        draft = await self._run_journalist(text)
        if not draft:
            return text # Если журналист упал, возвращаем оригинал

        # ШАГ 2: РЕДАКТОР (Gemini 2.0 Flash) - Верстка и стиль
        logger.info(f"--- Step 2: Editor ({MODEL_RU_EDITOR})")
        final_text = await self._run_editor(draft)
        
        return self._clean_output(final_text)

    async def _run_journalist(self, text: str) -> str:
        prompt = (
            "Ты — журналист. Твоя задача: выделить суть новости.\n"
            "1. Убери канцеляризмы ('в рамках реализации', 'согласно протоколу').\n"
            "2. Оставь только факты: цифры, даты, решения.\n"
            "3. Не придумывай ничего от себя.\n"
            "4. Напиши черновик простым языком."
        )
        try:
            model = genai.GenerativeModel(
                model_name=MODEL_RU_JOURNALIST,
                system_instruction=prompt
            )
            response = await asyncio.to_thread(
                model.generate_content,
                text,
                generation_config=genai.GenerationConfig(temperature=0.4)
            )
            return response.text
        except Exception as e:
            logger.error(f"Journalist Error: {e}")
            return None

    async def _run_editor(self, draft: str) -> str:
        prompt = (
            "Ты — Выпускающий Редактор. Отформатируй текст для Telegram.\n\n"
            "СТРОГИЕ ТРЕБОВАНИЯ:\n"
            "1. НИКАКИХ вводных слов ('Вот результат', 'Я поправил'). Начинай сразу с заголовка.\n"
            "2. Заголовок выдели тегом <b>...</b>.\n"
            "3. После заголовка — ОДНА пустая строка.\n"
            "4. Текст разбей на 2-3 плотных абзаца.\n"
            "5. В конце добавь 2-3 хэштега.\n"
            "6. Проверь факты: если журналист написал бред про 'раздачу денег', исправь на официальную формулировку.\n"
            "7. НЕ используй Markdown (**bold**), только HTML (<b>bold</b>)."
        )
        try:
            model = genai.GenerativeModel(
                model_name=MODEL_RU_EDITOR,
                system_instruction=prompt
            )
            response = await asyncio.to_thread(
                model.generate_content,
                draft,
                generation_config=genai.GenerationConfig(temperature=0.2)
            )
            return response.text
        except Exception as e:
            logger.error(f"Editor Error: {e}")
            return draft 

    def _clean_output(self, text: str) -> str:
        """Финальная чистка от мусора, если модель все-таки его выдала."""
        if not text: return ""
        
        # 1. Если модель выдала Markdown bold (**), меняем на HTML (<b>)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        
        # 2. Если модель начала с "Конечно, вот текст:", обрезаем до первого заголовка
        if "<b>" in text:
            start_index = text.find("<b>")
            text = text[start_index:]
            
        # 3. Убираем лишние пробелы и переносы
        text = text.strip()
        
        return text

rewriter = GeminiRewriter()

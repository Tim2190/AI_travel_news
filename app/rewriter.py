import logging
import re
import asyncio
from google import genai
from google.genai import types
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ (БЕЗ ИЗМЕНЕНИЙ) ---
MODEL_KZ = "gemini-2.5-flash"        
MODEL_RU_JOURNALIST = "gemini-2.0-flash" 
MODEL_RU_EDITOR = "gemini-2.0-flash"
MAX_TG_CAPTION_LEN = 800  

class GeminiRewriter:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            logger.error("CRITICAL: GEMINI_API_KEY is missing!")

    def _is_kazakh(self, text: str) -> bool:
        kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
        return bool(re.search(kz_chars, text, re.IGNORECASE))

    async def rewrite(self, text: str) -> str:
        if not text: return ""
        
        # Даем API "продышаться" перед новым запросом
        await asyncio.sleep(2) 

        if self._is_kazakh(text):
            return await self._process_kz(text)
        else:
            return await self._process_ru_pipeline(text)

    # --- КАЗАХСКИЙ ---
    async def _process_kz(self, text: str) -> str:
        logger.info(f"🇰🇿 KZ Pipeline: {MODEL_KZ}")
        
        system_prompt = (
            "Сен — кәсіби редакторсың. Мәтінді қазақ тілінде өңде.\n"
            f"ШЕКТЕУ: Мәтін {MAX_TG_CAPTION_LEN} символдан аспауы керек.\n"
            "ЕРЕЖЕЛЕР:\n"
            "1. Ешқандай кіріспе сөз жазба.\n"
            "2. Орысша сөздерді қолданба.\n"
            "3. Ресми, бірақ қысқа әрі түсінікті жаз.\n"
            "4. ТЕК ҚАНА МӘТІНДІ ҚАЙТАР.\n\n"
            "ҚҰРЫЛЫМ:\n"
            "<b>Тақырып</b>\n\n"
            "Негізгі мәтін (қысқаша).\n"
            "#хэштегтер"
        )

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=MODEL_KZ,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3
                )
            )
            return self._clean_output(response.text)
        except Exception as e:
            logger.error(f"KZ Error: {e}")
            return text[:MAX_TG_CAPTION_LEN]

    # --- РУССКИЙ (С ЗАЩИТОЙ ОТ ПЕРЕГРУЗКИ) ---
    async def _process_ru_pipeline(self, text: str) -> str:
        logger.info("🇷🇺 RU Pipeline Started...")

        # Шаг 1: Журналист
        draft = await self._run_agent(
            text, 
            role="Журналист",
            model=MODEL_RU_JOURNALIST,
            prompt="Выдели суть. Убери воду. Оставь только факты и цифры. Будь краток. Пиши понятно для всех людей",
            temp=0.4
        )
        if not draft: return text[:MAX_TG_CAPTION_LEN]

        # --- КРИТИЧЕСКАЯ ПРАВКА: Ждем 10 секунд перед следующим запросом ---
        # Это предотвращает 429 ошибку между шагами Journalist и Editor
        logger.info("⏳ Охлаждение API (10 сек)...")
        await asyncio.sleep(10)

        # Шаг 2: Редактор
        final_text = await self._run_agent(
            draft,
            role="Редактор",
            model=MODEL_RU_EDITOR,
            prompt=(
                "Ты — Выпускающий Редактор. Формат для Telegram.\n"
                f"СТРОГОЕ ОГРАНИЧЕНИЕ: Весь текст до {MAX_TG_CAPTION_LEN} символов.\n"
                "1. Начинай сразу с заголовка <b>...</b>.\n"
                "2. Текст должен быть плотным, без воды.\n"
                "3. Только HTML (<b>, <i>).\n"
                "4. В конце 2-3 хэштега."
            ),
            temp=0.2
        )
        return self._clean_output(final_text)

    async def _run_agent(self, content: str, role: str, model: str, prompt: str, temp: float) -> str:
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=model,
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    temperature=temp
                )
            )
            return response.text
        except Exception as e:
            # Если словили 429, логируем это четко
            if "429" in str(e):
                logger.warning(f"⚠️ {role} попал под лимит 429. Нужно больше времени на отдых.")
            else:
                logger.error(f"{role} Error: {e}")
            return content if role == "Редактор" else None

    def _clean_output(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        if "<b>" in text:
            text = text[text.find("<b>"):]
        if len(text) > MAX_TG_CAPTION_LEN:
            text = text[:MAX_TG_CAPTION_LEN-3] + "..."
        return text.strip()

rewriter = GeminiRewriter()

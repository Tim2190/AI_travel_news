import logging
import re
import asyncio
from google import genai
from google.genai import types
from groq import AsyncGroq # Не забудь добавить groq в requirements.txt
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ МОДЕЛЕЙ ---
MODEL_KZ = "gemini-2.5-flash"
MODEL_RU_GROQ = "meta-llama/llama-4-scout-17b-16e-instruct" # Топовая и быстрая модель на Groq
MAX_TG_CAPTION_LEN = 800

class GeminiRewriter:
    def __init__(self):
        # Инициализация Gemini
        if settings.GEMINI_API_KEY:
            self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            logger.error("CRITICAL: GEMINI_API_KEY is missing!")

        # Инициализация Groq
        if settings.GROQ_API_KEY:
            self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        else:
            logger.error("CRITICAL: GROQ_API_KEY is missing!")

    def _is_kazakh(self, text: str) -> bool:
        kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
        return bool(re.search(kz_chars, text, re.IGNORECASE))

    async def rewrite(self, text: str) -> str:
        if not text: return ""
        
        if self._is_kazakh(text):
            return await self._process_kz(text)
        else:
            return await self._process_ru_pipeline(text)

    # --- КАЗАХСКИЙ (GEMINI 2.5 FLASH) ---
    async def _process_kz(self, text: str) -> str:
        logger.info(f"🇰🇿 KZ Pipeline: {MODEL_KZ}")
        system_prompt = (
            "Сен — кәсіби редакторсың. Мәтінді қазақ тілінде өңде.\n"
            f"ШЕКТЕУ: Мәтін {MAX_TG_CAPTION_LEN} символдан аспауы керек.\n"
            "ЕРЕЖЕЛЕР:\n"
            "1. Ешқандай кіріспе сөз жазба. ТЕК ҚАНА МӘТІНДІ ҚАЙТАР.\n"
            "ҚҰРЫЛЫМ: <b>Тақырып</b>, бос жол, Негізгі мәтін, #хэштегтер"
        )
        try:
            response = await asyncio.to_thread(
                self.gemini_client.models.generate_content,
                model=MODEL_KZ,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3
                )
            )
            return self._clean_output(response.text)
        except Exception as e:
            logger.error(f"Gemini KZ Error: {e}")
            return text[:MAX_TG_CAPTION_LEN]

    # --- РУССКИЙ (GROQ / LLAMA 3.3) ---
    async def _process_ru_pipeline(self, text: str) -> str:
        logger.info(f"🇷🇺 RU Pipeline (GROQ): {MODEL_GROQ}")

        # Шаг 1: Журналист (Groq)
        draft = await self._run_groq_agent(
            text,
            prompt="Ты журналист. Сделай краткое изложение новости, убери воду и канцеляризмы. Оставь только факты. Будь краток."
        )
        if not draft: return text[:MAX_TG_CAPTION_LEN]

        # На Groq лимиты мягче, 2-3 секунды хватит за глаза
        await asyncio.sleep(2)

        # Шаг 2: Редактор (Groq)
        final_text = await self._run_groq_agent(
            draft,
            prompt=(
                "Ты — Выпускающий Редактор Telegram-канала.\n"
                f"ОГРАНИЧЕНИЕ: Весь текст до {MAX_TG_CAPTION_LEN} символов.\n"
                "1. Начинай сразу с заголовка <b>...</b>.\n"
                "2. Текст разбей на 2 абзаца. Используй только HTML (<b>, <i>).\n"
                "3. В конце 2-3 хэштега."
            )
        )
        return self._clean_output(final_text)

    async def _run_groq_agent(self, content: str, prompt: str) -> str:
        """Метод для работы с Groq API"""
        try:
            completion = await self.groq_client.chat.completions.create(
                model=MODEL_RU_GROQ,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq Agent Error: {e}")
            return None

    def _clean_output(self, text: str) -> str:
        if not text: return ""
        # Исправляем Markdown жирный на HTML если модель ошиблась
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        if "<b>" in text:
            text = text[text.find("<b>"):]
        if len(text) > MAX_TG_CAPTION_LEN:
            text = text[:MAX_TG_CAPTION_LEN-3] + "..."
        return text.strip()

rewriter = GeminiRewriter()

import logging
import re
import asyncio
from google import genai
from google.genai import types
from .config import settings

logger = logging.getLogger(__name__)

# --- НАСТРОЙКИ МОДЕЛЕЙ ---
MODEL_KZ = "gemini-2.5-flash"        

MODEL_RU_JOURNALIST = "gemini-2.0-flash" 
MODEL_RU_EDITOR = "gemini-2.0-flash"

class GeminiRewriter:
    def __init__(self):
        # Инициализация НОВОГО клиента (google.genai)
        if settings.GEMINI_API_KEY:
            self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            logger.error("CRITICAL: GEMINI_API_KEY is missing in settings!")

    def _is_kazakh(self, text: str) -> bool:
        """Определяет, является ли текст казахским по специфическим буквам."""
        kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
        return bool(re.search(kz_chars, text, re.IGNORECASE))

    async def rewrite(self, text: str) -> str:
        if not text:
            return ""

        if self._is_kazakh(text):
            return await self._process_kz(text)
        else:
            return await self._process_ru_pipeline(text)

    # =================================================================
    # ВЕТКА 1: КАЗАХСКИЙ ЯЗЫК (Твоя модель MODEL_KZ)
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
            logger.error(f"KZ Pipeline Error: {e}")
            return text

    # =================================================================
    # ВЕТКА 2: РУССКИЙ ЯЗЫК
    # =================================================================
    async def _process_ru_pipeline(self, text: str) -> str:
        logger.info("🇷🇺 RU Pipeline Started...")

        # ШАГ 1: ЖУРНАЛИСТ
        logger.info(f"--- Step 1: Journalist ({MODEL_RU_JOURNALIST})")
        draft = await self._run_agent(
            text, 
            role="Журналист",
            model=MODEL_RU_JOURNALIST,
            prompt=(
                "Ты — журналист. Твоя задача: выделить суть новости.\n"
                "1. Убери канцеляризмы ('в рамках реализации', 'согласно протоколу').\n"
                "2. Оставь только факты: цифры, даты, решения.\n"
                "3. Не придумывай ничего от себя.\n"
                "4. Напиши черновик простым языком."
            ),
            temp=0.4
        )
        if not draft: return text

        # ШАГ 2: РЕДАКТОР
        logger.info(f"--- Step 2: Editor ({MODEL_RU_EDITOR})")
        final_text = await self._run_agent(
            draft,
            role="Редактор",
            model=MODEL_RU_EDITOR,
            prompt=(
                "Ты — Выпускающий Редактор. Отформатируй текст для Telegram.\n\n"
                "СТРОГИЕ ТРЕБОВАНИЯ:\n"
                "1. НИКАКИХ вводных слов ('Вот результат', 'Я поправил'). Начинай сразу с заголовка.\n"
                "2. Заголовок выдели тегом <b>...</b>.\n"
                "3. После заголовка — ОДНА пустая строка.\n"
                "4. Текст разбей на 2-3 плотных абзаца.\n"
                "5. В конце добавь 2-3 хэштега.\n"
                "6. Проверь факты: если журналист написал бред про 'раздачу денег', исправь на официальную формулировку.\n"
                "7. НЕ используй Markdown (**bold**), только HTML (<b>bold</b>)."
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
            logger.error(f"{role} Error ({model}): {e}")
            return None if role == "Журналист" else content

    def _clean_output(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        if "<b>" in text:
            start_index = text.find("<b>")
            text = text[start_index:]
        return text.strip()

rewriter = GeminiRewriter()

import asyncio
import re
import logging
import google.generativeai as genai
from groq import Groq
from .config import settings

logger = logging.getLogger(__name__)

# --- ЖЕСТКИЕ ПРАВИЛА И СЛОВАРИ ---
KAZAQ_MONTHS = (
    "қаңтар, ақпан, наурыз, сәуір, мамыр, маусым, шілде, тамыз, қыркүйек, қазан, қараша, желтоқсан. "
    "Используй ТОЛЬКО эти названия."
)

LANGUAGE_RULES_KZ = (
    "ЯЗЫК: Текст должен быть на ЧИСТЕЙШЕМ КАЗАХСКОМ ЯЗЫКЕ. "
    "Строгий запрет на русизмы. Грамматика: Проверяй септік жалғаулары."
)

STYLE_ELI5 = (
    "СТИЛЬ: Объясняй 'на пальцах' (Explain Like I'm Five). "
    "Забудь про слова 'реализация', 'меморандум', 'в рамках программы'. "
    "Пиши так: 'Теперь цены будут такими...', 'Если вы пойдете в ЦОН, то...'. "
    "Представь, что ты пересказываешь новость другу, который вообще не понимает законы."
)

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

class HybridRewriter:
    def __init__(self):
        self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
        self.gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)

    def _is_kazakh(self, text: str) -> bool:
        kz_chars = r'[әіңғүұқөһӘІҢҒҮҰҚӨҺ]'
        return bool(re.search(kz_chars, text))

    async def rewrite(self, text: str) -> str:
        """Диспетчер: определяет язык и выбирает путь обработки."""
        if self._is_kazakh(text):
            return await self._process_gemini_kazakh(text)
        else:
            return await self._process_groq_russian_pipeline(text)

    # =================================================================
    # ПУТЬ 1: GEMINI (Казахский язык — Прямая линия)
    # =================================================================
    async def _process_gemini_kazakh(self, text: str) -> str:
        logger.info(">>> Путь KZ: Работает Gemini 2.5 Flash")
        prompt = (
            f"Сен — кәсіби қазақ тілді журналистсің. {LANGUAGE_RULES_KZ}\n"
            f"{STYLE_ELI5}\n"
            f"Ай аттары: {KAZAQ_MONTHS}\n"
            "ЗАДАЧА: Перепиши этот официальный текст максимально просто. Сделай его полезным для людей.\n"
            "ФОРМАТ: <b>Заголовок</b>\n\nТекст (2 абзаца).\n\n#теги\n\n"
            f"МӘТІН: {text}"
        )
        try:
            # Оборачиваем в асинхронный поток
            response = await asyncio.to_thread(self.gemini_model.generate_content, prompt)
            return self._sanitize_published_text(response.text)
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return None

    # =================================================================
    # ПУТЬ 2: GROQ (Русский язык — Конвейер 3-х ролей)
    # =================================================================
    async def _process_groq_russian_pipeline(self, text: str) -> str:
        logger.info(">>> Путь RU: Запуск конвейера GROQ (Журналист -> Редактор -> Главред)")
        
        # 1. ЖУРНАЛИСТ (Пишет черновик)
        j_system = (
            f"Ты — народный журналист. {STYLE_ELI5} "
            "Твоя цель: превратить скучный документ в интересную новость. "
            "Формат: <b>Заголовок</b>\n\nТекст."
        )
        draft = await self._call_groq_ai("Журналист", j_system, f"Разъясни эту новость простыми словами:\n{text}")
        if not draft: return None

        # 2. РЕДАКТОР (Проверка на простоту)
        e_system = (
            "Ты — Редактор. Если в тексте остались сложные слова, бюрократизмы или 'вода' — ответь REJECT. "
            "Если текст написан реально простым языком — ответь APPROVE."
        )
        decision = await self._call_groq_ai("Редактор", e_system, f"Оцени простоту текста. Ответь только APPROVE или REJECT:\n{draft}", max_tokens=10)
        
        if "REJECT" in decision.upper():
            logger.warning("Редактор GROQ отклонил текст за сложность.")
            return None

        # 3. ГЛАВРЕД (Финальная упаковка)
        p_system = (
           "Ты — Главный редактор. Твоя задача: навести лоск. "
            "Проверь длину: ТЕКСТ ДОЛЖЕН БЫТЬ СТРОГО ДО 800 ЗНАКОВ. " # Уменьшили запас для безопасности
            "Расставь абзацы, добавь 2-3 хэштега. "
            "Используй ТОЛЬКО тег <b> для заголовка и <i> для важных акцентов. "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать ссылки <a href...>. "
            "Обязательно сделай пустую строку после заголовка."            
        )
        final = await self._call_groq_ai("Главред", p_system, f"Сделай этот текст идеальным для Telegram:\n{draft}")
        
        return self._sanitize_published_text(final)

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ---

    async def _call_groq_ai(self, role: str, system: str, user: str, max_tokens=1000) -> str:
        """Универсальный вызов Groq с задержкой."""
        logger.info(f"--- {role} Groq в работе...")
        try:
            response = self.groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )
            # Пауза между ролями, чтобы не словить лимит
            await asyncio.sleep(settings.GROQ_DELAY_SECONDS)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Ошибка в роли {role}: {e}")
            return ""

    def _sanitize_published_text(self, text: str) -> str:
        """Глубокая очистка и форматирование."""
        if not text: return ""
        
        # 1. Убираем системный мусор ИИ
        for token in ["APPROVE", "REJECT", "DONE", "Here is the", "Revised text:"]:
            text = text.replace(token, "")
            
        # 2. Markdown Bold (**) в HTML (<b>)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        
        # 3. Лечим заголовки (чтобы не слипались)
        text = text.replace("</b>", "</b>\n\n")
        
        # 4. Убираем лишние пустые строки (максимум 2 подряд)
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        # 5. Обрезаем по умному
        return self.smart_truncate(text.strip())

    def smart_truncate(self, text: str, max_length: int = 950) -> str:
        if len(text) <= max_length:
            return text
        truncated = text[:max_length]
        last_sentence = -1
        for char in ['.', '!', '?']:
            pos = truncated.rfind(char)
            if pos > last_sentence:
                last_sentence = pos
        if last_sentence != -1:
            return truncated[:last_sentence+1]
        return truncated.rsplit(' ', 1)[0] + "..."

rewriter = HybridRewriter()

import asyncio
import re
import logging
from groq import Groq
from .config import settings

logger = logging.getLogger(__name__)

# --- СЛОВАРИ И ПРАВИЛА ---
KAZAQ_MONTHS = (
    "қаңтар, ақпан, наурыз, сәуір, мамыр, маусым, шілде, тамыз, қыркүйек, қазан, қараша, желтоқсан. "
    "Используй ТОЛЬКО эти названия."
)

LANGUAGE_RULES = (
    "ЯЗЫК: Текст должен быть на ЧИСТЕЙШЕМ КАЗАХСКОМ ЯЗЫКЕ. "
    "Строгий запрет на русизмы и англицизмы. "
    "Грамматика: Проверяй септік жалғаулары (падежи) и гармонию гласных."
)

# === НОВОЕ: ЗАПРЕТ НА КАНЦЕЛЯРИЗМЫ ===
STYLE_RULES = (
    "СТИЛЬ: Ты — автор, а не секретарь. "
    "ЗАПРЕТ НАЧИНАТЬ СО СЛОВ: '...хабарлауынша', '...мәліметі бойынша', 'Баспасөз қызметі', 'бойынша'. "
    "Начинай сразу с действия: 'Алматыда жаңа орынбасар...', 'Тоқаев қол қойды...', 'Тенге құлады...'."
)

class ContentRewriter:
    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def smart_truncate(self, text: str, max_length: int = 950) -> str:
        """Обрезает текст до лимита, сохраняя целостность предложений."""
        if len(text) <= max_length:
            return text
        
        truncated = text[:max_length]
        
        last_sentence_end = -1
        for char in ['.', '!', '?', '»', '"']:
            pos = truncated.rfind(char)
            if pos > last_sentence_end:
                last_sentence_end = pos
        
        if last_sentence_end != -1:
            return truncated[:last_sentence_end+1]
        
        last_space = truncated.rfind(' ')
        if last_space != -1:
            return truncated[:last_space] + "..."
            
        return truncated

    async def rewrite(self, text: str) -> str:
        """
        Пайплайн: Журналист (Креатив) -> Редактор (Фильтр) -> Полировщик (Стиль + Лимит).
        """
        
        # 1. ЖУРНАЛИСТ
        journalist_system = (
            "Ты — колумнист интеллектуального журнала в стиле 'Сноб' или 'Esquire'. "
            "Твоя задача: написать короткую заметку на основе новости. "
            "СТИЛЬ: Ироничный, умный, с контекстом. "
            "ЯЗЫК: ТОЛЬКО КАЗАХСКИЙ. "
            f"{LANGUAGE_RULES} "
            f"{STYLE_RULES} " # Добавили правила стиля
            f"Месяцы: {KAZAQ_MONTHS}"
        )
        
        journalist_user = f"""
        Напиши заметку на основе этого текста.
        
        ТРЕБОВАНИЯ К ФОРМАТУ:
        1. Заголовок: Выдели тегом <b>Заголовок</b>.
        2. Объем: СТРОГО до 850 символов.
        3. Структура: 2-3 абзаца. 
        4. Подача: Сразу к сути. Легкая ирония в конце.
        5. Хэштеги: 2-3 штуки в конце.
        
        ИСХОДНЫЙ ТЕКСТ:
        {text}
        """
        
        draft = await self._call_ai("Журналист", journalist_system, journalist_user)
        if not draft: return None
        draft = draft.strip()
        
        # 2. РЕДАКТОР
        editor_system = "Ты — строгий главред. Ответь APPROVE или REJECT."
        editor_user = f"""
        Оцени текст. 
        Если это скучный пресс-релиз или спам — REJECT.
        Если это живой текст — APPROVE.
        ТЕКСТ: {draft}
        """
        decision = await self._call_ai("Редактор", editor_system, editor_user, max_tokens=10)
        
        if "REJECT" in decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        # 3. ПОЛИРОВЩИК
        polisher_system = (
            "Ты — корректор. Твоя цель — сделать текст идеальным и коротким. "
            f"{LANGUAGE_RULES}"
        )
        
        polisher_user = f"""
        Отредактируй этот текст для публикации в Telegram.
        
        ЗАДАЧИ:
        1. ДЛИНА: Строго до 900 символов.
        2. СТРУКТУРА: Обязательно делай пустую строку между абзацами!
        3. ФОРМАТ: Оставь HTML теги <b></b> для заголовка.
        
        ТЕКСТ: {draft}
        """
        
        final_text = await self._call_ai("Полировщик", polisher_system, polisher_user)
        if not final_text: return None

        final_text = self._sanitize_published_text(final_text)
        final_text = self.smart_truncate(final_text, max_length=950)
        
        return final_text

    async def _call_ai(self, role: str, system_prompt: str, user_prompt: str, max_tokens=900) -> str:
        logger.info(f"Этап: {role} работает...")
        try:
            messages = [
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7, 
            )
            result = response.choices[0].message.content.strip()
            
            delay = getattr(settings, "GROQ_DELAY_SECONDS", 20)
            if delay > 0:
                logger.info(f"Пауза {delay}с...")
                await asyncio.sleep(delay)
                
            return result
        except Exception as e:
            logger.error(f"Ошибка {role}: {e}")
            return "" 

    def _sanitize_published_text(self, text: str) -> str:
        stripped = text.strip()
        # Удаляем служебные ответы
        for token in ["APPROVE", "REJECT", "ACCEPT", "DONE", "Here is the text"]:
            stripped = stripped.replace(token, "")
            
        # Чистка Markdown в HTML
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", stripped)
        
        # === ИСПРАВЛЕНИЕ ЗАГОЛОВКА ===
        # Принудительно добавляем два переноса строки после закрывающего тега заголовка
        stripped = stripped.replace("</b>", "</b>\n\n")
        
        # Убираем лишние множественные переносы (если вдруг их стало 3 и больше)
        stripped = re.sub(r"\n{3,}", "\n\n", stripped)
        
        return stripped.strip()

rewriter = ContentRewriter(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
)

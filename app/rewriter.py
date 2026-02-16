import asyncio
import re
import logging
from groq import Groq
from .config import settings

logger = logging.getLogger(__name__)

# --- СЛОВАРИ И ПРАВИЛА ---
# Словари оставляем, они важны для чистоты языка
KAZAQ_MONTHS = (
    "қаңтар, ақпан, наурыз, сәуір, мамыр, маусым, шілде, тамыз, қыркүйек, қазан, қараша, желтоқсан. "
    "Используй ТОЛЬКО эти названия. Никаких 'февраль' или 'February'."
)

# Правила чистоты (инструкция на русском для модели)
LANGUAGE_RULES = (
    "ЯЗЫК: Текст должен быть на ЧИСТЕЙШЕМ КАЗАХСКОМ ЯЗЫКЕ. "
    "Строгий запрет на русизмы и англицизмы (никаких 'particularly', 'однако', 'в частности'). "
    "Используй: 'әсіресе' вместо 'particularly', 'алайда' вместо 'однако/however'. "
    "Грамматика: Проверяй падежные окончания (септік жалғаулары) и гармонию гласных."
)

class ContentRewriter:
    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def smart_truncate(self, text: str, max_length: int = 950) -> str:
        """Обрезает текст до лимита, сохраняя целостность предложений."""
        if len(text) <= max_length:
            return text
        
        # Обрезаем жестко
        truncated = text[:max_length]
        
        # Ищем последние знаки препинания, чтобы не оборвать на полуслове
        # Приоритет: точка, восклицательный, вопросительный, кавычка
        last_sentence_end = -1
        for char in ['.', '!', '?', '»', '"']:
            pos = truncated.rfind(char)
            if pos > last_sentence_end:
                last_sentence_end = pos
        
        if last_sentence_end != -1:
            return truncated[:last_sentence_end+1]
        
        # Если знаков нет, ищем хотя бы пробел
        last_space = truncated.rfind(' ')
        if last_space != -1:
            return truncated[:last_space] + "..."
            
        return truncated

    async def rewrite(self, text: str) -> str:
        """
        Пайплайн: Журналист (Креатив) -> Редактор (Фильтр) -> Полировщик (Стиль + Лимит).
        """
        
        # 1. ЖУРНАЛИСТ: Пишет креативно, в стиле Сноб
        journalist_system = (
            "Ты — колумнист интеллектуального журнала в стиле 'Сноб' или 'Esquire'. "
            "Твоя задача: написать короткую заметку на основе новости. "
            "СТИЛЬ: Ироничный, умный, с контекстом. Не просто 'что случилось', а 'что это значит'. "
            "ЯЗЫК: ТОЛЬКО КАЗАХСКИЙ. "
            f"{LANGUAGE_RULES} "
            f"Месяцы: {KAZAQ_MONTHS}"
        )
        
        journalist_user = f"""
        Напиши заметку на основе этого текста.
        
        ТРЕБОВАНИЯ К ФОРМАТУ:
        1. Заголовок: Выдели тегом <b>Заголовок</b> (на казахском).
        2. Объем: СТРОГО до 850 символов (это критично для Telegram). Пиши кратко, без воды.
        3. Структура: 2-3 абзаца. 
        4. Подача: Добавь легкую иронию или аналитический комментарий в конце.
        5. Хэштеги: 2-3 штуки в конце.
        
        ИСХОДНЫЙ ТЕКСТ:
        {text}
        """
        
        draft = await self._call_ai("Журналист", journalist_system, journalist_user)
        if not draft: return None
        draft = draft.strip()
        
        # 2. РЕДАКТОР: Проверка на адекватность
        editor_system = "Ты — строгий главред. Твоя задача — пропустить новость (APPROVE) или отклонить (REJECT)."
        editor_user = f"""
        Оцени этот текст. 
        Если это скучный пресс-релиз, спам, реклама или бред — ответь REJECT.
        Если это нормальная новость с иронией/смыслом — ответь APPROVE.
        
        ТЕКСТ: {draft}
        """
        decision = await self._call_ai("Редактор", editor_system, editor_user, max_tokens=10)
        
        if "REJECT" in decision.upper():
            logger.warning("Редактор отклонил новость (скучно или мусор).")
            return None

        # 3. ПОЛИРОВЩИК: Финальная чистка языка и лимитов
        polisher_system = (
            "Ты — корректор и лингвист. Твоя цель — сделать текст идеальным и коротким. "
            f"{LANGUAGE_RULES}"
        )
        
        polisher_user = f"""
        Отредактируй этот текст для публикации в Telegram.
        
        ЗАДАЧИ:
        1. ПРОВЕРЬ ДЛИНУ: Текст ОБЯЗАН быть короче 900 символов. Если длиннее — сокращай безжалостно, убирай лишние слова.
        2. ПРОВЕРЬ ЯЗЫК: Исправь все окончания (септіктер), убери русские/английские слова.
        3. ФОРМАТ: Оставь HTML теги <b></b> для заголовка.
        4. Верни ТОЛЬКО готовый текст.
        
        ТЕКСТ ДЛЯ ОБРАБОТКИ:
        {draft}
        """
        
        final_text = await self._call_ai("Полировщик", polisher_system, polisher_user)
        if not final_text: return None

        # Финальная страховка кодом (обрезаем, если ИИ все-таки выдал много)
        final_text = self._sanitize_published_text(final_text)
        final_text = self.smart_truncate(final_text, max_length=950)
        
        return final_text

    async def _call_ai(self, role: str, system_prompt: str, user_prompt: str, max_tokens=900) -> str:
        logger.info(f"Этап: {role} работает...")
        try:
            # ВОТ ТУТ БЫЛА ОШИБКА, ТЕПЕРЬ ИСПРАВЛЕНО:
            messages = [
                {"role": "system", "content": system_content}, 
                {"role": "user", "content": user_prompt}
            ]
            messages[0]["content"] = system_prompt # Явное присвоение для надежности
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7, 
            )
            result = response.choices[0].message.content.strip()
            
            # Пауза для защиты от лимитов
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
        
        return stripped

rewriter = ContentRewriter(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
)

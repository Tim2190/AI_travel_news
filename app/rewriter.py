import logging
from huggingface_hub import InferenceClient
from .config import settings

logger = logging.getLogger(__name__)

class ContentRewriter:
    def __init__(self, api_key: str, model_journalist: str, model_editor: str):
        self.client = InferenceClient(api_key=api_key)
        self.model_journalist = model_journalist
        self.model_editor = model_editor

    async def rewrite(self, text: str) -> str:
        """
        Многоступенчатая обработка: Журналист -> Редактор -> Главред.
        """
        journalist_prompt = f"""Вы — профессиональный журналист туристического медиа.
ЗАДАЧА: Переведите и переработайте источник в качественную новость на русском языке, готовую к публикации.

STRICT RULES:
1) Используйте формальный, литературный русский. Не придумывайте слова и не используйте жаргон.
2) Не меняйте географию: локации должны полностью соответствовать источнику.
3) Не добавляйте факты: работайте только с тем, что есть в источнике.
4) Один пост = одна конкретная новость. Не смешивайте разные темы.
5) Формат для Telegram: один цепляющий заголовок, 3–5 коротких абзацев, 2–3 релевантных эмодзи.
6) Выведите ТОЛЬКО финальный текст новости на русском. Без рассуждений и служебных пометок.

Source:
{text}"""
        draft = await self._call_ai("Журналист", journalist_prompt, self.model_journalist)
        draft = draft.strip()
        
        editor_prompt = f"""Вы — редактор туристического медиа. Оцените текст на новостную ценность, качество и фактологическую корректность.

RULES:
1) Если текст низкого качества, малозначимый или искажает факты — ответ ТОЛЬКО: REJECT
2) Если текст качественный и соответствует фактам — ответ ТОЛЬКО: APPROVE

Без объяснений. Ответьте ровно одним словом: REJECT или APPROVE.

Text:
{draft}"""
        editor_decision = await self._call_ai("Редактор", editor_prompt, self.model_editor)
        
        if "REJECT" in editor_decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        chief_editor_prompt = f"""Вы — главный редактор. Проверьте текст на соответствие законодательству о СМИ и базовой этике.

GUIDELINES:
1) Будьте разумны: блокируйте только явные юридические/этические нарушения.
2) Если есть нарушение — ответ ТОЛЬКО: REJECT
3) Если публикация безопасна — ответ ТОЛЬКО: APPROVE

Без объяснений. Ответьте ровно одним словом: REJECT или APPROVE.

Text:
{draft}"""
        chief_decision = await self._call_ai("Бас редактор", chief_editor_prompt, self.model_editor)

        if "REJECT" in chief_decision.upper():
            logger.warning("Главный редактор отклонил новость.")
            return None

        # Финальная языковая полировка (строго без изменений фактов и географии)
        polisher_prompt = f"""Вы — русскоязычный литературный редактор туристического медиа.
Отредактируйте следующий текст БЕЗ изменения фактов и географии, и БЕЗ добавления новой информации.
Требования: формальный стиль, чёткая структура (3–5 коротких абзацев), единая тема, корректная грамматика и терминология.
Выведите ТОЛЬКО финальный текст новости на русском. Без объяснений.

Text:
{draft}"""
        final_text = await self._call_ai("Тіл редакторы", polisher_prompt, self.model_editor)
        final_text = final_text.strip()

        # Если текст выглядит незавершенным, аккуратно завершить
        if self._looks_incomplete(final_text):
            completer_prompt = f"""Продолжите следующий новостной текст на русском и естественно завершите его.
Не повторяйте начало, не добавляйте новых фактов сверх источника, соблюдайте формальный стиль.
Верните ТОЛЬКО завершение/продолжение на русском.

Text:
{final_text}"""
            completion = await self._call_ai("Жабушы", completer_prompt, self.model_editor)
            final_text = (final_text + "\n" + completion.strip()).strip()

        return self._sanitize_published_text(final_text)

    async def _call_ai(self, role: str, prompt: str, model: str) -> str:
        logger.info(f"Этап: {role} ({model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Вы — профессиональный {role} туристического медиа. Всегда отвечайте на русском (ru-RU)."},
                {"role": "user", "content": prompt}
            ]
            response = self.client.chat_completion(
                messages=messages,
                model=model,
                max_tokens=2000,
                temperature=0.7,
            )
            result = response.choices[0].message.content.strip()
            logger.info(f"{role} завершил работу. Длина текста: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Ошибка на этапе {role}: {str(e)}")
            raise e

    def _looks_incomplete(self, text: str) -> bool:
        if not text:
            return True
        end = text.strip()[-1]
        return end not in [".", "!", "?", "…", "»", "”"]

    def _sanitize_published_text(self, text: str) -> str:
        # Удаление возможных служебных маркеров, если модель их вернула
        stripped = text.strip()
        upper = stripped.upper()
        if upper in ["APPROVE", "REJECT", "ACCEPT", "OK"]:
            return ""
        # Фильтрация очевидных служебных префиксов/суффиксов
        for token in ["APPROVE", "REJECT", "ACCEPT"]:
            stripped = stripped.replace(token, "")
        return stripped.strip()

rewriter = ContentRewriter(
    api_key=settings.HF_API_KEY, 
    model_journalist=settings.HF_MODEL_JOURNALIST,
    model_editor=settings.HF_MODEL_EDITOR
)

import logging
from groq import Groq
from .config import settings

logger = logging.getLogger(__name__)

class ContentRewriter:
    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    async def rewrite(self, text: str) -> str:
        """
        Многоступенчатая обработка: Журналист -> Редактор -> Главред.
                """
        journalist_prompt = f"""Ты — журналист-райтер молодежного экономического медиа.
ЗАДАЧА: Перескажи источник живым, современным языком для зумеров и альфа-поколения.

СТИЛЬ:
1) Русский язык, но лёгкий, разговорный, без канцелярита.
2) Можно лёгкий сленг, мемные обороты и эмодзи, но БЕЗ мата и оскорблений.
3) Ориентируйся на аудиторию 18–30: короткие предложения, динамика, чуть иронии.

СМЫСЛ:
1) Географию не меняй: страны и города должны совпадать с источником.
2) Факты не выдумывай: работай только с тем, что есть в исходном тексте.
3) Один пост = одна новость. Не мешай несколько тем в одну кашу.

ФОРМАТ:
1) В начале — короткий, цепляющий заголовок в ОДНОЙ строке, БЕЗ символов #.
2) Ниже 3–5 абзацев по 1–3 предложения, без разметки Markdown.
3) Используй 2–4 подходящих эмодзи по смыслу.
4) Выведи ТОЛЬКО финальный текст поста для Telegram, без пояснений и служебных пометок.

ИСТОЧНИК:
{text}"""
        draft = await self._call_ai("Журналист", journalist_prompt)
        draft = draft.strip()
        
        editor_prompt = f"""Вы — редактор экономического медиа. Оцените текст на новостную ценность, качество и фактологическую корректность.

RULES:
1) Если текст низкого качества, малозначимый или искажает факты — ответ ТОЛЬКО: REJECT
2) Если текст качественный и соответствует фактам — ответ ТОЛЬКО: APPROVE

Без объяснений. Ответьте ровно одним словом: REJECT или APPROVE.

Text:
{draft}"""
        editor_decision = await self._call_ai("Редактор", editor_prompt)
        
        if "REJECT" in editor_decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        chief_editor_prompt = f"""Вы — главный редактор экономического медиа. Проверьте текст на соответствие законодательству о СМИ и базовой этике.

GUIDELINES:
1) Будьте разумны: блокируйте только явные юридические/этические нарушения.
2) Если есть нарушение — ответ ТОЛЬКО: REJECT
3) Если публикация безопасна — ответ ТОЛЬКО: APPROVE

Без объяснений. Ответьте ровно одним словом: REJECT или APPROVE.

Text:
{draft}"""
        chief_decision = await self._call_ai("Бас редактор", chief_editor_prompt)

        if "REJECT" in chief_decision.upper():
            logger.warning("Главный редактор отклонил новость.")
            return None

        # Финальная языковая полировка (строго без изменений фактов и географии)
        polisher_prompt = f"""Вы — русскоязычный редактор стиля молодежного экономического медиа.
Отредактируйте следующий текст БЕЗ изменения фактов и географии, и БЕЗ добавления новой информации.
Требования: формальный стиль, чёткая структура (3–5 коротких абзацев), единая тема, корректная грамматика и терминология.
Выведите ТОЛЬКО финальный текст новости на русском. Без объяснений.

Text:
{draft}"""
        final_text = await self._call_ai("Редактор стиля", polisher_prompt)
        final_text = final_text.strip()

        # Если текст выглядит незавершенным, аккуратно завершить
        if self._looks_incomplete(final_text):
            completer_prompt = f"""Продолжите следующий новостной текст на русском и естественно завершите его.
Не повторяйте начало, не добавляйте новых фактов сверх источника, соблюдайте формальный стиль.
Верните ТОЛЬКО завершение/продолжение на русском.

Text:
{final_text}"""
            completion = await self._call_ai("Завершение", completer_prompt)
            final_text = (final_text + "\n" + completion.strip()).strip()

        return self._sanitize_published_text(final_text)

    async def _call_ai(self, role: str, prompt: str) -> str:
        logger.info(f"Этап: {role} ({self.model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Ты — профессиональный {role} в русскоязычном экономическом медиа. Всегда отвечай по-русски."},
                {"role": "user", "content": prompt}
            ]
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=900,
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
        stripped = text.strip()
        upper = stripped.upper()
        if upper in ["APPROVE", "REJECT", "ACCEPT", "OK"]:
            return ""
        for token in ["APPROVE", "REJECT", "ACCEPT"]:
            stripped = stripped.replace(token, "")
        lines = stripped.splitlines()
        cleaned_lines = []
        for line in lines:
            l = line.lstrip()
            if l.startswith("### "):
                cleaned_lines.append(l[4:])
            elif l.startswith("## "):
                cleaned_lines.append(l[3:])
            elif l.startswith("# "):
                cleaned_lines.append(l[2:])
            else:
                cleaned_lines.append(line)
        return "\n".join(x.strip() for x in cleaned_lines).strip()

rewriter = ContentRewriter(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
)

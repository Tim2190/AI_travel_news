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
        journalist_prompt = f"""You are a professional journalist at a Kazakh tourism media.
TASK: Translate and rewrite the following source into high-quality Kazakh suitable for publication.

STRICT RULES:
1) Use formal, literary Kazakh only. Do not invent words or use mixed slang.
2) Do not change geography. Keep locations exactly as in the source.
3) Do not add facts. Use only information present in the source.
4) One post = one specific news story. Do not merge multiple topics.
5) Format for a Telegram post: one catchy headline, 3–5 short paragraphs, and 2–3 relevant emojis.
6) Output ONLY the final news text in Kazakh. No reasoning, no meta-comments, no explanations.

Source:
{text}"""
        draft = await self._call_ai("Журналист", journalist_prompt, self.model_journalist)
        draft = draft.strip()
        
        editor_prompt = f"""You are an editor at a Kazakh tourism media. Evaluate the text for newsworthiness, quality, and factual consistency.

RULES:
1) If the text is low-quality, insignificant, or distorts facts, reply ONLY with: REJECT
2) If the text is good and factually consistent, reply ONLY with: APPROVE

NO explanations. Reply with exactly one word: REJECT or APPROVE.

Text:
{draft}"""
        editor_decision = await self._call_ai("Редактор", editor_prompt, self.model_editor)
        
        if "REJECT" in editor_decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        chief_editor_prompt = f"""You are the chief editor. Check the text for compliance with Kazakhstan media law and general ethics.

GUIDELINES:
1) Be reasonable: only block content with clear legal/ethical violations.
2) If there is a violation, reply ONLY with: REJECT
3) If it is safe to publish, reply ONLY with: APPROVE

NO explanations. Reply with exactly one word: REJECT or APPROVE.

Text:
{draft}"""
        chief_decision = await self._call_ai("Бас редактор", chief_editor_prompt, self.model_editor)

        if "REJECT" in chief_decision.upper():
            logger.warning("Главный редактор отклонил новость.")
            return None

        # Финальная языковая полировка (строго без изменений фактов и географии)
        polisher_prompt = f"""You are a Kazakh language proofreader for a tourism media.
Polish the following Kazakh text WITHOUT changing facts or locations, and WITHOUT adding any new information.
Ensure: formal style, clear structure (3–5 short paragraphs), single-topic coherence, correct grammar and terminology.
Output ONLY the final news text in Kazakh. Do not include explanations.

Text:
{draft}"""
        final_text = await self._call_ai("Тіл редакторы", polisher_prompt, self.model_editor)
        final_text = final_text.strip()

        # Если текст выглядит незавершенным, аккуратно завершить
        if self._looks_incomplete(final_text):
            completer_prompt = f"""Continue the following Kazakh news text naturally and conclude it.
Do NOT repeat the beginning, do NOT add new facts beyond the source, and keep formal style.
Return ONLY the continuation/completion in Kazakh.

Text:
{final_text}"""
            completion = await self._call_ai("Жабушы", completer_prompt, self.model_editor)
            final_text = (final_text + "\n" + completion.strip()).strip()

        return self._sanitize_published_text(final_text)

    async def _call_ai(self, role: str, prompt: str, model: str) -> str:
        logger.info(f"Этап: {role} ({model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"You are a professional {role} for a Kazakh tourism media. Always respond in Kazakh (kk-KZ)."},
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

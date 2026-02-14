import logging
from huggingface_hub import InferenceClient
from .config import settings

logger = logging.getLogger(__name__)

class ContentRewriter:
    def __init__(self):
        self.client = InferenceClient(
            token=settings.HF_API_KEY,
            # provider="hf-inference" is used by default in recent versions or via specific kwargs
        )
        self.model = settings.HF_MODEL

    async def rewrite(self, text: str) -> str:
        """
        Реализует многоступенчатую логику рерайта:
        1. Копирайтер (черновик на казахском)
        2. Редактор (проверка стиля и фактов)
        3. Главный редактор (финальная шлифовка)
        """
        
        # Шаг 1: Копирайтер
        copywriter_prompt = f"Сделай качественный перевод и рерайт этой новости на казахский язык. Текст должен быть информативным и интересным для туристов:\n\n{text}"
        draft = await self._call_ai("Копирайтер", copywriter_prompt)
        
        # Шаг 2: Редактор
        editor_prompt = f"Проверь этот текст на казахском языке. Улучши стиль, исправь ошибки и сделай его более вовлекающим для читателей из Казахстана:\n\n{draft}"
        edited_text = await self._call_ai("Редактор", editor_prompt)
        
        # Шаг 3: Главный редактор
        chief_editor_prompt = f"Ты главный редактор туристического СМИ. Дай финальную версию этой новости на казахском. Добавь цепляющий заголовок в начале, используй эмодзи и оформи текст для Telegram-канала:\n\n{edited_text}"
        final_text = await self._call_ai("Главный редактор", chief_editor_prompt)
        
        return final_text

    async def _call_ai(self, role: str, prompt: str) -> str:
        logger.info(f"Этап: {role} работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Сіз кәсіби қазақстандық туризм журналының {role} қызметін атқарасыз."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(
                messages=messages,
                model=self.model,
                max_tokens=1500,
                temperature=0.7,
                # provider="hf-inference" удален, так как вызывает ошибку
            )
            result = response.choices[0].message.content.strip()
            logger.info(f"{role} завершил работу. Длина текста: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Ошибка на этапе {role}: {str(e)}")
            raise e

rewriter = ContentRewriter()

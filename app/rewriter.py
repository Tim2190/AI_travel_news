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
        Если на любом этапе текст не проходит проверку, возвращается None.
        """
        # Шаг 1: Журналист (Qwen2.5-72B) - Перевод и качественный рерайт на казахский
        journalist_prompt = f"""Сіз кәсіби туризм журналисісіз. Төмендегі жаңалықты қазақ тіліне сапалы аударып, қызықты рерайт жасаңыз. 
Жаңалықтың мәнін сақтап, оқырманға тартымды етіп жазыңыз.

Жаңалық мәтіні:
{text}
"""
        draft = await self._call_ai("Журналист", journalist_prompt, self.model_journalist)
        
        # Шаг 2: Редактор (Llama-3.1-8B) - Проверка значимости
        # Если текст пустой или не имеет ценности, редактор должен вернуть "REJECT"
        editor_prompt = f"""Сіз туристік басылымның редакторысыз. Төмендегі жаңалықтың маңыздылығын тексеріңіз. 
Егер бұл жаңалық оқырман үшін маңызды болмаса немесе мағынасыз болса, тек қана "REJECT" сөзін жазыңыз. 
Егер жаңалық жақсы болса, оның қазақ тіліндегі стилистикасын жақсартып, түзетілген нұсқасын қайтарыңыз.

Тексерілетін мәтін:
{draft}
"""
        edited_text = await self._call_ai("Редактор", editor_prompt, self.model_editor)
        
        if "REJECT" in edited_text.upper() and len(edited_text) < 20:
            logger.warning("Редактор отклонил новость как малозначимую.")
            return None

        # Шаг 3: Главный редактор (Llama-3.1-8B) - Проверка на грубые нарушения и оформление
        chief_editor_prompt = f"""Сіз Қазақстандық туристік БАҚ-тың Бас редакторысыз. 
Мәтінді тексеріп, оның этикалық нормаларға сәйкестігін және Қазақстан заңнамасын өрескел бұзбайтынына көз жеткізіңіз. 
Цензураға тым қатты берілмеңіз, тек ең сорақы заң бұзушылықтарды ғана өткізбеңіз.

МАҢЫЗДЫ: 
1. Егер мәтін жариялауға мүлдем жарамсыз болса, тек "REJECT" сөзін қайтарыңыз.
2. Егер бәрі дұрыс болса, төмендегі мәтінді ЕШҚАНДАЙ ӨЗГЕРІССІЗ толығымен қайтарыңыз. "ACCEPT" немесе басқа сөздерді қоспаңыз, тек жаңалықтың өзін қайтарыңыз.

Тексерілетін мәтін:
{edited_text}
"""
        final_text = await self._call_ai("Бас редактор", chief_editor_prompt, self.model_editor)

        if "REJECT" in final_text.upper() and len(final_text) < 20:
            logger.warning("Главный редактор отклонил новость.")
            return None
            
        # Если главред вернул слишком короткое подтверждение вместо текста, берем текст редактора
        if len(final_text) < 50 and any(word in final_text.upper() for word in ["ACCEPT", "OK", "ИӘ", "МАҚҰЛ"]):
            logger.info("Бас редактор подтвердил публикацию коротким словом. Используем текст редактора.")
            return edited_text

        return final_text

    async def _call_ai(self, role: str, prompt: str, model: str) -> str:
        logger.info(f"Этап: {role} ({model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Сіз кәсіби қазақстандық туризм журналының {role} қызметін атқарасыз. Тек қазақ тілінде жауап беріңіз."},
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

rewriter = ContentRewriter(
    api_key=settings.HF_API_KEY, 
    model_journalist=settings.HF_MODEL_JOURNALIST,
    model_editor=settings.HF_MODEL_EDITOR
)

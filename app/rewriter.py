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
        # Шаг 1: Журналист (Qwen2.5-72B) - Качественный перевод и рерайт
        journalist_prompt = f"""Сіз кәсіби қазақстандық туризм журналисісіз. 
ТАПСЫРМА: Төмендегі мәтінді қазақ тіліне аударып, тартымды жаңалық жазыңыз.

ҚАТАҢ ЕРЕЖЕЛЕР:
1. Тек қана ресми және әдеби қазақ тілін қолданыңыз. "Мадани мұнайтысы" сияқты ойдан шығарылған сөздерді қолдануға ТЫЙЫМ салынады.
2. ГЕОГРАФИЯНЫ ӨЗГЕРТПЕҢІЗ: Егер оқиға Еуропада болса, ол Еуропа болып қалуы тиіс. Оқиғаны Қазақстанға телімеңіз.
3. ФАКТІЛЕРДІ ОЙДАН ШЫҒАРМАҢЫЗ: Тек түпнұсқада бар ақпаратты қолданыңыз.
4. Мәтін Telegram арнасына арналған: қызықты заголовок, құрылымдалған мәтін және 2-3 эмодзи қолданыңыз.

Түпнұсқа мәтін:
{text}
"""
        draft = await self._call_ai("Журналист", journalist_prompt, self.model_journalist)
        
        # Шаг 2: Редактор (Llama-3.1-8B) - Проверка качества и ценности
        editor_prompt = f"""Сіз туристік басылымның редакторысыз. Төмендегі мәтінді сапа мен маңыздылыққа тексеріңіз.

ЕРЕЖЕ:
1. Егер мәтін сапасыз, мағынасыз немесе фактілер бұрмаланған болса, ТЕК ҚАНА "REJECT" сөзін жазыңыз.
2. Егер мәтін жақсы болса, ТЕК ҚАНА "APPROVE" сөзін жазыңыз.

ЕШҚАНДАЙ ТҮСІНІКТЕМЕ ЖАЗБАҢЫЗ. ТЕК БІР СӨЗ: REJECT НЕМЕСЕ APPROVE.

Мәтін:
{draft}
"""
        editor_decision = await self._call_ai("Редактор", editor_prompt, self.model_editor)
        
        if "REJECT" in editor_decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        # Шаг 3: Главный редактор (Llama-3.1-8B) - Юридическая проверка
        chief_editor_prompt = f"""Сіз Бас редакторсыз. Мәтінді заңнамалық және этикалық нормаларға тексеріңіз.

ЕРЕЖЕ:
1. Егер мәтінде ҚР заңнамасын бұзу немесе этикаға жат нәрсе болса, ТЕК ҚАНА "REJECT" сөзін жазыңыз.
2. Егер бәрі дұрыс болса, ТЕК ҚАНА "APPROVE" сөзін жазыңыз.

ЕШҚАНДАЙ ТҮСІНІКТЕМЕ ЖАЗБАҢЫЗ. ТЕК БІР СӨЗ: REJECT НЕМЕСЕ APPROVE.

Мәтін:
{draft}
"""
        chief_decision = await self._call_ai("Бас редактор", chief_editor_prompt, self.model_editor)

        if "REJECT" in chief_decision.upper():
            logger.warning("Главный редактор отклонил новость.")
            return None

        # Если оба одобрили, возвращаем чистый текст от журналиста
        return draft

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

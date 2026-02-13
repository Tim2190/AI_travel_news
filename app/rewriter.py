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
        Rewrites the input text into Kazakh language for a tourism news channel.
        Implements a multi-step prompt logic (Copywriter -> Editor -> Chief Editor).
        """
        prompt = f"""
        Сіз кәсіби қазақстандық туризм саласындағы журналистсіз. 
        Төмендегі жаңалықты қазақ тілінде қайта жазып шығыңыз.
        
        Жаңалық тақырыбы: Туризм және саяхат.
        Стиль: Қызықты, ақпараттық, оқырманға жақын.
        Тіл: Қазақ тілі.
        
        Түпнұсқа мәтін:
        {text}
        
        Тапсырма:
        1. Мәтінді қазақ тіліне сапалы аударып, туризмге бағытталған стильде өңдеңіз.
        2. Оқырманға пайдалы кеңестер немесе қызықты деректер қосыңыз (мүмкін болса).
        3. Құрылымын жақсартыңыз: тартымды тақырып, негізгі бөлім, қорытынды.
        
        Тек қана дайын мәтінді қайтарыңыз.
        """
        
        try:
            # Using chat_completion for better instruction following and provider support
            messages = [
                {"role": "system", "content": "Сіз кәсіби қазақстандық туризм саласындағы журналистсіз (копирайтер, редактор және бас редактор рөлдерін атқарасыз)."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(
                messages=messages,
                model=self.model,
                max_tokens=1500,
                temperature=0.7,
                provider="hf-inference"
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error during rewriting: {str(e)}")
            raise e

rewriter = ContentRewriter()

import re
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
        journalist_prompt = f"""Сен — жастарға арналған экономикалық медиа журналист-райтері.
МІНДЕТ: Дереккөзді жанды, заманауи қазақ тілінде қайта жаз. Жастар (18–30) үшін түсінікті, бірақ тіл таза болуы керек.

СТИЛЬ:
1) Тек ҚАЗАҚ тілі. Жастар сөйлеу тіліне жақын, жеңіл, бірақ фанатизмсіз — грамматикалық тазалық сақталады.
2) Күнделікті сөздер, қысқа сөйлемдер рұқсат. Мат пен қорлау ЖОҚ.
3) Эмодзи міндетті: 3–5 тақырыпқа сәйкес иконка/эмодзи қой (жаңалық, экономика, қала, т.б.).

МАҒЫНА:
1) Географияны өзгертпе: елдер мен қалалар дереккөздегідей қалады.
2) Фактілерді ойдан шығарма, тек дереккөздегі ақпаратпен жұмыс істе.
3) Бір пост = бір жаңалық. Бірнеше тақырыпты араластырма.

ФОРМАТ (маңызды):
1) Тақырыпты HTML қалыбында жаз: <b>тақырып мәтіні</b> — жалғыз жолда. Звездочка ** ҚОЛДАНБА.
2) Төменде 3–5 абзац, әрқайсысы 1–3 сөйлем. Абзацтар арасында эмодзи болуы керек.
3) Мәтінің соңына 2–3 хэштег қос (мысалы #Жаңалық #Қазақстан #Экономика — тақырыпқа байланысты).
4) Шығарманың соңында тек Telegram постының мәтінін бер, түсініктеме жоқ.

ДЕРЕККӨЗ:
{text}"""
        draft = await self._call_ai("Журналист", journalist_prompt)
        draft = draft.strip()
        
        editor_prompt = f"""Сен экономикалық медиа редакторысың. Мәтінді жаңалық құндылығы, сапасы және фактілердің дұрыстығы бойынша бағала.

ЕРЕЖЕ:
1) Мәтін сапасыз, маңызсыз немесе фактілерді бұрмаласа — жауап тек: REJECT
2) Мәтін сапалы және фактілерге сәйкес келсе — жауап тек: APPROVE

Түсініктеме жоқ. Бір сөзмен жауап бер: REJECT немесе APPROVE.

Мәтін:
{draft}"""
        editor_decision = await self._call_ai("Редактор", editor_prompt)
        
        if "REJECT" in editor_decision.upper():
            logger.warning("Редактор отклонил новость.")
            return None

        chief_editor_prompt = f"""Сен экономикалық медиа бас редакторысың. Мәтінді БАҚ заңнамасына және негізгі этикаға сәйкестігін тексер.

ЕРЕЖЕ:
1) Тек анық заңды/этикалық бұзушылықтар болса — REJECT.
2) Бұзушылық бар болса — жауап тек: REJECT
3) Жариялау қауіпсіз болса — жауап тек: APPROVE

Түсініктеме жоқ. Бір сөзмен: REJECT немесе APPROVE.

Мәтін:
{draft}"""
        chief_decision = await self._call_ai("Бас редактор", chief_editor_prompt)

        if "REJECT" in chief_decision.upper():
            logger.warning("Главный редактор отклонил новость.")
            return None

        # Финальная языковая полировка (строго без изменений фактов и географии)
        polisher_prompt = f"""Сен жастар экономикалық медиасының қазақ тілі редакторысың.
Келесі мәтінді фактілер мен географиюны ӨЗГЕРТПЕЙ, жаңа ақпарат ҚОСПАЙ түзет.
Талаптар: қазақ тілінің тазалығы, грамматика дұрыстығы, нақты құрылым (3–5 қысқа абзац), бір тақырып.
Шығарманың соңында ТЕК қазақша жаңалық мәтінін бер. Түсініктеме жоқ.

Мәтін:
{draft}"""
        final_text = await self._call_ai("Редактор стиля", polisher_prompt)
        final_text = final_text.strip()

        # Если текст выглядит незавершенным, аккуратно завершить
        if self._looks_incomplete(final_text):
            completer_prompt = f"""Келесі жаңалық мәтінін қазақша жалғастырып, табиғи түрде аяқта.
Басын қайталама, дереккөзден тыс жаңа факті қоспа, таза қазақ тілін сақта.
Тек аяқталу бөлігін қазақша қайтар.

Мәтін:
{final_text}"""
            completion = await self._call_ai("Завершение", completer_prompt)
            final_text = (final_text + "\n" + completion.strip()).strip()

        return self._sanitize_published_text(final_text)

    async def _call_ai(self, role: str, prompt: str) -> str:
        logger.info(f"Этап: {role} ({self.model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Сен экономикалық медиада кәсіби {role}. Жауаптарды қазақ тілінде бер (редактор/бас редактор этабында REJECT/APPROVE сөздерін ағылшынша қалдыр)."},
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
        # Telegram использует HTML: **текст** → <b>текст</b>
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", stripped)
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

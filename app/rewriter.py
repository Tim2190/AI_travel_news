import asyncio
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
        journalist_prompt = f"""Сен — «СНОБ» журналы стилінде жазатын автор: ойлы, контексті бар, сенімді дауысы бар. Тілі — қазақ.
МІНДЕТ: Дереккөзді қайта жазуды емес, оны түсіндіруді, «неге маңызды» деп сұрауды мақсат ет. Подача — журнал колонкасы сияқты: көзқарас бар, контекст бар, жеңіл ирония мүмкін, бірақ фактілер өзгермейді.

ПОДАЧА (СНОБ стилі):
1) Аноним бюллетень емес — автордың дауысы: «біз көрдік», «қызығы», «нақты айтқанда» сияқты түсініктемелер рұқсат, бірақ шамалы.
2) Тек «не болды» емес — «не білдіреді»: қысқа контекст, салдар немесе неге бұл жаңалық. Көлемі үлкен емес, бір-екі сөйлем.
3) Жеңіл ирония, ақылды юмор — рұқсат; мат, қорлау, ашық саяси тарап — жоқ. Аудитория — ойлайтын, білімді оқырман.
4) Қазақ тілі таза, грамматика дұрыс. Стиль — журналдық: тілдік деңгей жоғары, бірақ түсінікті.

МАҒЫНА:
1) География мен фактілер дереккөздегідей. Ойдан факті қоспа.
2) Бір пост = бір тақырып. Подачаны өзгерт, мазмұнды емес.

ФОРМАТ:
1) Тақырып — HTML: <b>тақырып</b> бір жолда. ** ҚОЛДАНБА.
2) 3–5 абзац, әрқайсысы 1–3 сөйлем. Абзацтар арасында 3–5 эмодзи.
3) Соңына 2–3 хэштег (тақырыпқа сәйкес).
4) ҰЗЫНДЫҚ: барлық мәтін строго 950 таңбадан кем. Total length must be strictly under 950 characters.
5) Шығарманың соңында тек постың мәтінін бер, түсініктеме жоқ.

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

        # Финальная полировка: сохранить подачу в стиле СНОБ, не сплющить до «просто новость»
        polisher_prompt = f"""Сен «СНОБ» стилін сақтайтын редакторсың. Мәтінді түзетсің, бірақ автордың дауысын, контекст пен жеңіл иронияны ЖОҒАЛТПА.
Фактілер мен географиюны ӨЗГЕРТПЕЙ, жаңа факті ҚОСПАЙ. Тек тіл мен құрылымды әдебі түзет: таза қазақ, дұрыс грамматика, 3–5 абзац, бір тақырып.
Нәтиже — журнал колонкасы сияқты қысқа, ойлы текст. Барлық мәтін строго 950 таңбадан кем (Total length must be strictly under 950 characters). Шығарманың соңында ТЕК финалды мәтінді бер. Түсініктеме жоқ.

Мәтін:
{draft}"""
        final_text = await self._call_ai("Редактор стиля", polisher_prompt)
        final_text = final_text.strip()

        # Если текст выглядит незавершенным, аккуратно завершить
        if self._looks_incomplete(final_text):
            completer_prompt = f"""Келесі мәтінді қазақша жалғастырып, табиғи аяқта. Стиль сақталады: журнал колонкасы сияқты, контекст/көзқарас бар.
Басын қайталама, жаңа факті қоспа. Тек аяқталу бөлігін қайтар.
ЖҰМЫС МІНДЕТТІ ШЕК: барлық жауап (осы мәтін + жалғасы) строго 950 таңбадан кем болуы керек. Total length must be strictly under 950 characters.

Мәтін:
{final_text}"""
            completion = await self._call_ai("Завершение", completer_prompt)
            final_text = (final_text + "\n" + completion.strip()).strip()

        return self._sanitize_published_text(final_text)

    async def _call_ai(self, role: str, prompt: str) -> str:
        logger.info(f"Этап: {role} ({self.model}) работает над текстом...")
        try:
            messages = [
                {"role": "system", "content": f"Сен экономикалық медиада кәсіби {role}. Стиль — журнал «СНОБ»: автордық дауыс, контекст, жеңіл ирония, фактіге сүйену. Жауаптар қазақша (редактор/бас редакторда тек REJECT немесе APPROVE)."},
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
            # Пауза между запросами к Groq, чтобы не превысить TPM (лимит токенов в минуту)
            delay = getattr(settings, "GROQ_DELAY_SECONDS", 20)
            if delay > 0:
                logger.info(f"Пауза {delay} с перед следующим запросом к Groq...")
                await asyncio.sleep(delay)
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

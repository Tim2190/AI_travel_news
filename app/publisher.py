import logging
import re
from telegram import Bot
from telegram.constants import ParseMode
from .config import settings

logger = logging.getLogger(__name__)

# Лимит подписи к фото в Telegram (1024), обрезаем до 1000 с запасом
TELEGRAM_CAPTION_MAX_LEN = 1000


def truncate_caption(text: str, max_len: int = TELEGRAM_CAPTION_MAX_LEN) -> str:
    """
    Умная обрезка: если текст не влезает, удаляем HTML-теги, 
    чтобы не оставить незакрытых сущностей.
    """
    if not text:
        return ""
    
    # 1. Если текст и так влезает, просто возвращаем
    if len(text) <= max_len:
        return text

    # 2. Если НЕ влезает — это значит ИИ выдал слишком много.
    # Чтобы не искать незакрытые <b> или <a>, мы просто чистим текст от HTML.
    logger.warning("Caption too long (%s chars). Stripping HTML and truncating.", len(text))
    
    # Удаляем все теги <...>
    clean_text = re.sub('<[^<]+?>', '', text)
    
    # 3. Если после очистки всё еще длинно — режем до лимита
    if len(clean_text) > max_len:
        return clean_text[:max_len - 3].rstrip() + "..."
    
    return clean_text

class TelegramPublisher:
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.chat_id = settings.TELEGRAM_CHAT_ID

    async def publish(self, text: str, image_url: str = None) -> int:
        """
        Publishes the news to the Telegram channel.
        Returns the message_id of the published post.
        """
        text = truncate_caption(text)
        try:
            if image_url:
                message = await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=image_url,
                    caption=text,
                    parse_mode=ParseMode.HTML
                )
            else:
                message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
            return message.message_id
        except Exception as e:
            logger.error(f"Error publishing to Telegram: {str(e)}")
            raise e

publisher = TelegramPublisher()

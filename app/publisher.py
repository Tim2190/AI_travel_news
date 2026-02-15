import logging
from telegram import Bot
from telegram.constants import ParseMode
from .config import settings

logger = logging.getLogger(__name__)

# Лимит подписи к фото в Telegram (1024), обрезаем до 1000 с запасом
TELEGRAM_CAPTION_MAX_LEN = 1000


def truncate_caption(text: str, max_len: int = TELEGRAM_CAPTION_MAX_LEN) -> str:
    """Обрезает текст под лимит подписи Telegram. Если ИИ вышел за рамки — принудительно режем."""
    if not text or len(text) <= max_len:
        return text or ""
    out = text[:max_len].rstrip()
    # Не обрывать на полпути HTML-тега или entity
    while out and out[-1] in ("<", "&"):
        out = out[:-1].rstrip()
    if len(text) > max_len:
        logger.warning("Caption truncated from %s to %s characters.", len(text), len(out))
    return out


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

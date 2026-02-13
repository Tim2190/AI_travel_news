import logging
from telegram import Bot
from telegram.constants import ParseMode
from .config import settings

logger = logging.getLogger(__name__)

class TelegramPublisher:
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.chat_id = settings.TELEGRAM_CHAT_ID

    async def publish(self, text: str, image_url: str = None) -> int:
        """
        Publishes the news to the Telegram channel.
        Returns the message_id of the published post.
        """
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

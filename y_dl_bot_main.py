from __future__ import unicode_literals

import asyncio
import logging
import os
import pprint
import re
import traceback
from urllib.parse import urlparse
from urllib.request import urlopen, Request

from bs4 import BeautifulSoup
import yt_dlp as youtube_dl
from telegram import error, Update
from telegram.ext import MessageHandler, CommandHandler, ApplicationBuilder, ContextTypes, filters
from telegram.helpers import escape_markdown

from secret import telegram_secret

# ignoreList = ["9gag.com"]
ignoreList = ["twitch.tv", "www.twitch.tv"]


async def signal_handler(signum, frame):
    raise Exception("Timed out!")


def my_hook(d):
    if d['status'] == 'finished':
        logger.info("Download finished.")


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger()

ydl_opts = {
    'format': 'bestvideo[ext=mp4][filesize<30M]+bestaudio[ext=m4a]/bestvideo[filesize<30M][ext=mp4]+bestaudio/best['
              'ext=mp4][filesize<35M]/best[filesize<35M]/bestvideo*[filesize<30M]+bestaudio/bestvideo*+bestaudio/bestvideo+bestaudio/best',
    'outtmpl': '%(id)s.%(ext)s',
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4'
    }],
    'logger': logger,
    'progress_hooks': [my_hook],
}

logger.setLevel(logging.INFO)

application = ApplicationBuilder().token(telegram_secret).concurrent_updates(
    concurrent_updates=True).connection_pool_size(connection_pool_size=8).pool_timeout(360).build()


# updater = Updater(token=telegram_secret, workers=8)
# dispatcher = updater.dispatcher


def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


def error_callback(update, context):
    raise context.error


async def get_title(url: str) -> [str, None]:
    """
    Extract the title of a post

    :param url: The URL of the post
    :return: The extracted title or None in case a title could not be found
    """
    try:
        response = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}))
    except Exception as exception:
        logger.warning(f"Downloading HTML document {url} for title parsing failed: {exception}")
        return None

    if response.status != 200:
        logger.warning(f"Got status code {response.status} while trying to download HTML doc {url} for title parsing")
        return None

    title_tag = None
    parsed_url = urlparse(response.geturl())
    soup = BeautifulSoup(response.read(), "html.parser")

    if "reddit.com" in parsed_url.netloc:
        title_h1s = soup.find_all('h1', {"id": re.compile("post-title.*")})
        if title_h1s:
            title_tag = title_h1s[0]

        if not title_tag:
            title_divs = soup.find_all("div", {"data-adclicklocation": "title"})
            if title_divs:
                title_tag = title_divs[0].find("h1")

        if not title_tag:
            logger.warning("Reddit changed their layout, update parser")
            return None
    else:
        titles = soup.find_all("title")
        if not titles:
            logger.warning("No title found")
            return None
        title_tag = titles[0]
    logger.info("Title fetch finished.")
    return title_tag.get_text()


async def link_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None and update.channel_post is None:
        return
    text = update.message.text or update.channel_post.text
    url = ""
    urls = re.findall(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", text)

    if urls:
        logger.info("Got URL(s): " + pprint.pformat(urls))
        title_fetcher = None
        for url in urls:
            if urlparse(url).netloc in ignoreList:
                logger.info("Skipping ignored host.")
                continue
            else:
                logger.info("Got netloc: " + urlparse(url).netloc)

            title_fetcher = asyncio.create_task(get_title(url))
            logger.info("Fetching video!")
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    # ydl_results = ydl.download(url=url, download=True)
                    try:
                        new_message = await context.bot.send_message(chat_id=update.effective_chat.id,
                                                                     text="Trying to fetch video...",
                                                                     disable_notification=True)
                        logger.debug("Extracting url info.")
                        result = ydl.extract_info(url=url)
                        logger.debug("setting up message.")
                        logger.debug("downloading file")
                        result = ydl.extract_info(url=url, process=True)
                        logger.debug("getting file-name")
                        ydl_filename = ydl.prepare_filename(result)
                    except youtube_dl.utils.DownloadError as e:
                        if 'new_message' in locals():
                            await context.bot.deleteMessage(chat_id=update.effective_chat.id,
                                                            message_id=new_message.message_id)
                    except:
                        logger.error(traceback.format_exc())
            except:
                logger.error(traceback.format_exc())

        if 'ydl_filename' in locals() and ydl_filename:
            logger.info("Downloaded video: " + pprint.pformat(ydl_filename))
            file = None
            # We need a lot of workarounds because YoutubeDL sometimes messes with file names
            try:
                file = open(ydl_filename, 'rb')
            except FileNotFoundError as e:
                logger.warning("File not found: " + ydl_filename)
            if not file:
                try:
                    file = open(os.path.splitext(ydl_filename)[0] + '.mp4', 'rb')
                except FileNotFoundError as e:
                    logger.error("Even the mp4 does not exist for: " + ydl_filename)
                    await context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)
            if file:
                caption_text = escape_markdown("Source: " + url, version=2)
                if title_fetcher:
                    title = await title_fetcher
                    if title:
                        caption_text = f"*{escape_markdown(title, version=2)}*\n\n{caption_text}"

                logger.info(f"Caption is : {caption_text}")
                try:
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=file, supports_streaming=True,
                                                 write_timeout=120, connect_timeout=120, pool_timeout=120,
                                                 caption=caption_text,
                                                 disable_notification=True,
                                                 reply_to_message_id=update.message.message_id, parse_mode='MarkdownV2')
                except error.NetworkError as e:
                    logger.warning("Upload failed: " + e.message)
                finally:
                    await context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)


def ping(update):
    update.message.reply_text('pong')


link_handler = MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.UpdateType.MESSAGE, link_handle)

application.add_handler(link_handler)
application.add_error_handler(error_callback)
application.add_handler(CommandHandler("ping", ping))

application.run_polling()

from __future__ import unicode_literals

import logging
import pprint
import re
import os

import youtube_dl
from telegram import InputMediaVideo
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater
from telegram.ext.dispatcher import run_async

from secret import telegram_secret


def my_hook(d):
    if d['status'] == 'finished':
        logger.info("Download finished.")


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger()

ydl_opts = {
    'format': 'bestvideo[ext=mp4,filesize<20M]+bestaudio[ext=m4a]/bestvideo[filesize<20M,ext=mp4]+bestaudio/best[ext=mp4,filesize<25M]/best[filesize<25M]/best',
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4'
    }],
    'logger': logger,
    'progress_hooks': [my_hook],
}

logger.setLevel(logging.INFO)

updater = Updater(token=telegram_secret, use_context=True, workers=5)
dispatcher = updater.dispatcher


def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


@run_async
def link_handle(update, context):
    if update.message is None and update.channel_post is None:
        return
    text = update.message.text or update.channel_post.text

    urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

    if urls:
        logger.info("Got URL(s): " + pprint.pformat(urls))
        for url in urls:
            logger.info("Trying URL: " + url)
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                # ydl_results = ydl.download(url=url, download=True)
                try:
                    result = ydl.extract_info(url=url, download=False)
                    new_message = context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text="Trying to fetch video...", disable_notification=True)
                    result = ydl.extract_info(url=url, download=True)
                    ydl_filename = ydl.prepare_filename(result)
                except youtube_dl.utils.DownloadError as e:
                    if 'new_message' in locals():
                        context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)

            if 'ydl_filename' in locals() and ydl_filename:
                logger.info("Downloaded video: " + pprint.pformat(ydl_filename))
                video = InputMediaVideo(open(ydl_filename, 'rb'))
                caption_text = "Source: " + url
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
                        context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)

                context.bot.send_video(chat_id=update.effective_chat.id, video=open(ydl_filename, 'rb'),
                                       supports_streaming=True, timeout=60, caption=caption_text)

            context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)


link_handler = MessageHandler(Filters.text & (~Filters.command) & Filters.update.message, link_handle)
dispatcher.add_handler(link_handler)

updater.start_polling()
updater.idle()

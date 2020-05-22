from __future__ import unicode_literals
import logging
import re
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater
from telegram import InputTextMessageContent, InputMediaVideo
import youtube_dl
import pprint


def my_hook(d):
    if d['status'] == 'finished':
        print('Done downloading, now converting ...')


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger()

ydl_opts = {
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegVideoConvertor',
        'preferedformat': 'mp4'
    }],
    'logger': logger,
    'progress_hooks': [my_hook],
}

logger.setLevel(logging.INFO)

updater = Updater(token='TOKEN', use_context=True)
dispatcher = updater.dispatcher


def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")


def link_handle(update, context):
    pprint.pprint(update)
    pprint.pprint(context)
    if update.message is None and update.channel_post is None:
        return
    text = update.message.text or update.channel_post.text

    urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

    if urls:
        logger.info("Got URL(s): " + pprint.pformat(urls))
        for url in urls:
            logger.info("Trying URL: " + url)
            ydl = youtube_dl.YoutubeDL
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                # ydl_results = ydl.download(url=url, download=True)
                try:
                    result = ydl.extract_info(url=url, download=False)
                    new_message = context.bot.send_message(chat_id=update.effective_chat.id,
                                                           text="Trying to fetch video...")
                    result = ydl.extract_info(url=url, download=True)
                    ydl_filename = ydl.prepare_filename(result)
                except youtube_dl.utils.DownloadError as e:
                    if 'new_message' in locals():
                        context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)

            if 'ydl_filename' in locals() and ydl_filename:
                logger.info("Downloaded video: " + pprint.pformat(ydl_filename))
                video = InputMediaVideo(open(ydl_filename, 'rb'))
                context.bot.send_video(chat_id=update.effective_chat.id, video=open(ydl_filename, 'rb'),
                                       supports_streaming=True)
                context.bot.deleteMessage(chat_id=update.effective_chat.id, message_id=new_message.message_id)


link_handler = MessageHandler(Filters.text & (~Filters.command) & Filters.update.message, link_handle)
dispatcher.add_handler(link_handler)

updater.start_polling()

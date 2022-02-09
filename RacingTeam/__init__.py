#!/usr/bin/python3
import json
import html
import logging
import traceback
from telegram import ParseMode, Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    Updater,
)

from .private import DEVELOPER_CHAT_ID, BOT_TOKEN

logger = logging.getLogger()

updater = Updater(
    token=BOT_TOKEN,
    use_context=True,
    arbitrary_callback_data=True,
)


def start(update: Update, context: CallbackContext):
    welcome = """Hallo,
ich versuche dir Auskunft über aktuelle Fahrpläne, Abfahrten und Verbindungen zu geben.

Für Abfahrten schick mir einfach den Haltestellennamen oder einen Standort 📍.

Für Verbindungen nutz einfach /route. 
"""
    update.message.reply_text(text=welcome)


def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
    # Notify user
    update.effective_chat.send_message(
        "Entschuldigung irgendetwas ist schiefgelaufen, probier es noch einmal."
    )

def help(update: Update, context: CallbackContext):
    update.effective_message.reply_markdown(
        quote=True,
        text="Ich versuche dir Auskunft über aktuelle Fahrpläne, Abfahrten und Verbindungen zu geben.\n"
        "\n"
        "*Abfahrten*\n"
        "Für Abfahrten schick mir einfach den Namen der Haltestelle oder einen Standort📍.\n"
        "\n"
        "*Verbindungssuche*\n"
        "/route `START ZIEL`\n"
        "/route `START`\n"
        "/route\n"
        "Ich versuche dir eine Verbindung zwischen _START_ und _ZIEL_ zu finden, "
        "du kannst auch nur einen Start oder auch gar nichts angeben, "
        "dann frage ich dich später nach einem Ziel / Start und Ziel. "
        "Natürlich kannst du mir dann auch für das Ziel einen Standort📍 schicken.\n"
        "\n"
        "*Favoriten*\n"
        "Du kannst Haltestellen, bei der Abfahrtssuche als Favoriten⭐️ hinzufügen."
        "Mit /fav zeige ich dir deine gespeicherten Haltestellen dann an.\n"
        "\n"
        "*Sonstiges*\n"
        "/cancel\n"
        "Brich einen anderen Befehl ab.\n"
        "\n"
        "*Hilfe*\n"
        "/help\n"
        "Ich schicke dir diese Nachricht 😉\n"
        "\n"
    )


def init():
    dispatcher = updater.dispatcher
    from . import departures, route

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help))
    dispatcher.add_handler(route.handler)
    # Put departure handlers into group 1 to prevent issues with route handlers
    [dispatcher.add_handler(handler, 1) for handler in departures.handlers]

    dispatcher.add_error_handler(error_handler)


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )

    init()
    updater.start_polling()

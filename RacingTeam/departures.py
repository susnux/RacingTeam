from __future__ import annotations

from math import ceil
from pydoc import resolve
import vvo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
)

from .base import QueryTag, get_data, get_stop_data, pattern_valid_tag

DEPARTURES_LIMIT = 5
DEPARTURES_LIMIT_MAX = 10


# Common helpers


def keyboard_select_stop(stops: list[vvo.Point], tag: QueryTag):
    """Create keyboard for stop selection"""
    return [
        [
            InlineKeyboardButton(
                stop.name
                + (
                    f" ({stop.distance} m)"
                    if stop.distance
                    else (f" ({stop.place})" if stop.place else "")
                ),
                callback_data=(tag, (stop.id,)),
            )
        ]
        for stop in stops
    ]


def handle_stop_message(update: Update, tag=QueryTag.STOP_SELECTED):
    """Handle a stop message (name or location)

    Args:
        update: Telegram update object
        tag: QueryTag to set for multiple selection callback
    """
    if update.message.location:
        location = update.message.location
        query = (location.longitude, location.latitude)
    else:
        query = update.message.text.strip()
    response = vvo.find_stops(query, shortcuts=True, limit=3)
    if len(response.points) == 0:
        update.effective_message.reply_text(
            quote=True, text="Entschuldigung 😔, aber ich konnte keine Haltestellen finden."
        )
        return False, None
    elif len(response.points) > 1:
        update.effective_message.reply_text(
            quote=True,
            text="Ich habe mehrere Haltestellen gefunden, bitte wähle eine aus:",
            reply_markup=InlineKeyboardMarkup(keyboard_select_stop(response.points, tag)),
        )
        return True, None
    else:
        return True, response.points[0]


####################################################################
# Main logic
def departures(stop: vvo.Point, favorites, more=False, time=None):
    """Helper to create message of departures and keyboard markup

    Args:
        stop: Stop to query departures
        more: Show more departures than normal
        time: Begin of departures
    """
    if not stop.is_stop:
        raise ValueError("stop has to be as stop, not a point!")

    limit = DEPARTURES_LIMIT_MAX if more else DEPARTURES_LIMIT
    response = vvo.get_departures(stop, shorttermchanges=True, limit=limit, time=time)

    message = (
        f"Abfahrten für *{response.name}*"
        + (f" ({response.place})" if response.place and response.place != "Dresden" else "")
        + (f" _[{stop.shortcut}]_\n" if stop.shortcut else "\n")
    )
    keyboard = [
        [
            InlineKeyboardButton("📍 Standort", callback_data=(QueryTag.STOP_LOCATION, (stop.id,))),
            InlineKeyboardButton(
                "⭐️ Favorit" if stop.id not in favorites else "🚫 Favorit entfernen",
                callback_data=(QueryTag.STOP_FAVORITE, (stop.id,)),
            ),
        ]
    ]

    if not response.departures:
        message += "Aktuell keine Abfahren."
    else:
        pad_line = max([len(d.line_name) for d in response.departures])
        pad_dir = max([len(d.direction) for d in response.departures])
        for departure in response.departures:
            message += f"`{departure.line_name.rjust(pad_line)} {departure.direction.rjust(pad_dir)} {ceil(departure.departure/60)}`\n"

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🕓 Später",
                    callback_data=(
                        QueryTag.DEPARTURE_LATER,
                        (
                            stop.id,
                            (
                                response.departures[-1].real_time
                                or response.departures[-1].scheduled
                            ).isoformat(),
                        ),
                    ),
                ),
            ]
        )
        if response.more:
            keyboard[1].append(
                InlineKeyboardButton(
                    "➕ Mehr",
                    callback_data=(
                        QueryTag.DEPARTURE_MORE,
                        (stop.id,),
                    ),
                )
            )

    return message, keyboard


##########################################################
# Callbacks


def cb_departures_query(update: Update, context: CallbackContext, stop=None):
    """Called when responded to inline query (select stop)"""
    tag, stop, data = get_stop_data(update)
    time = data[0] if data else None
    message, keyboard = departures(
        stop,
        favorites=context.user_data.get("favorites", []),
        more=tag == QueryTag.DEPARTURE_MORE,
        time=time,
    )
    update.effective_chat.send_message(
        message, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
    )


def cb_departures_location(update: Update, context: CallbackContext):
    """Find departures by location or message"""
    success, point = handle_stop_message(update)
    if success and point:
        message, keyboard = departures(point, favorites=context.user_data.get("favorites", []))
        update.effective_message.reply_markdown(
            message,
            quote=True,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def cb_stop_location(update: Update, context: CallbackContext):
    """Send requested stop location"""
    tag, stop, data = get_stop_data(update)
    update.effective_chat.send_location(stop.location[1], stop.location[0])


def cb_favorite_edit(update: Update, context: CallbackContext):
    """Favorite or unfavorite a stop"""
    tag, stop, data = get_stop_data(update)
    fav = context.user_data.get("favorites", {})
    if stop.id in fav:
        del fav[stop.id]
    else:
        fav[stop.id] = stop.name
    context.user_data["favorites"] = fav
    if update.effective_message.reply_markup:
        kb = update.effective_message.reply_markup.inline_keyboard
        kb[0][1] = InlineKeyboardButton(
            text="⭐️ Favorit" if (stop.id not in fav) else "🚫 Favorit entfernen",
            callback_data=(QueryTag.STOP_FAVORITE, (stop.id,)),
        )
        update.effective_message.edit_reply_markup(InlineKeyboardMarkup(kb))


def cb_favorites(update: Update, context: CallbackContext):
    fav = context.user_data.get("favorites", {})
    if not fav:
        update.message.reply_text("Du hast bisher keine favorisierten Haltestellen.")
    else:
        kb = [
            [InlineKeyboardButton(name, callback_data=(QueryTag.STOP_SELECTED, (id,)))]
            for id, name in fav.items()
        ]
        update.message.reply_text(
            "Deine favorisierten Haltestellen:", reply_markup=InlineKeyboardMarkup(kb)
        )


handlers = [
    MessageHandler(
        Filters.location | (Filters.text & (~Filters.command)), callback=cb_departures_location
    ),
    CommandHandler("fav", callback=cb_favorites),
    CallbackQueryHandler(
        callback=cb_departures_query,
        pattern=pattern_valid_tag([QueryTag.DEPARTURE_MORE, QueryTag.STOP_SELECTED], [int]),
    ),
    CallbackQueryHandler(
        callback=cb_departures_query,
        pattern=pattern_valid_tag(QueryTag.DEPARTURE_LATER, [int, str]),
    ),
    CallbackQueryHandler(
        callback=cb_stop_location, pattern=pattern_valid_tag(QueryTag.STOP_LOCATION, [int])
    ),
    CallbackQueryHandler(
        callback=cb_favorite_edit, pattern=pattern_valid_tag(QueryTag.STOP_FAVORITE, [int])
    ),
]

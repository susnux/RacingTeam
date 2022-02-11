import vvo
from typing import Iterable, Optional
from telegram import ChatAction, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    DispatcherHandlerStop,
    Filters,
    MessageHandler,
)

from RacingTeam.departures import handle_stop_message, keyboard_select_stop
from .base import QueryTag, get_stop_data, pattern_valid_tag

# settings
NUMBER_ROUTES = 3

# states
QUERY_START = 1
QUERY_DEST = 2


def is_typing(update: Update):
    update.effective_chat.send_chat_action(ChatAction.TYPING, 120)


def routes(start, end) -> tuple[str, Optional[list]]:
    """Generate routes message and keyboard"""

    def map_type(vehicle: vvo.Vehicle):
        if vehicle.type == vvo.TransportationType.FOOTPATH:
            return "➡️", "Fußweg", ""
        elif vehicle.type == vvo.TransportationType.STAY:
            return "🔄", "Auf Verbindung warten", ""
        elif (
            vehicle.type == vvo.TransportationType.STAIRWAY_UP
            or vehicle.type == vvo.TransportationType.RAMP_UP
        ):
            return (
                "⬆️",
                "Treppe" if vehicle.type == vvo.TransportationType.STAIRWAY_UP else "Rampe",
                "hoch",
            )
        elif (
            vehicle.type == vvo.TransportationType.STAIRWAY_DOWN
            or vehicle.type == vvo.TransportationType.RAMP_DOWN
        ):
            return (
                "⬇️",
                "Treppe" if vehicle.type == vvo.TransportationType.STAIRWAY_UP else "Rampe",
                "runter",
            )
        return "➡️", vehicle.name, vehicle.direction

    resp = vvo.find_routes(start, end, limit=NUMBER_ROUTES)
    if not resp.ok or len(resp.routes) == 0:
        return "Ich konnte keine Verbindungen finden 😔.", None

    kb = [
        [
            InlineKeyboardButton("Start 📍", callback_data=(QueryTag.STOP_LOCATION, (start.id,))),
            InlineKeyboardButton("Ziel 📍", callback_data=(QueryTag.STOP_LOCATION, (end.id,))),
        ]
    ]
    message = f"Verbindungen `{resp.routes[0].partial_routes[0].stops[0].name}` 👉 `{resp.routes[0].partial_routes[-1].stops[-1].name}`"
    for idx, route in enumerate(resp.routes[: min(NUMBER_ROUTES, len(resp.routes))]):
        message += f"\n{chr(0x31 + idx)}{chr(0xFE0F)}{chr(0x20E3)} *{route.partial_routes[0].stops[0].departure.strftime('%H:%M')} - {route.partial_routes[-1].stops[-1].arrival.strftime('%H:%M')}* ({route.duration} min)"
        for sub_idx, sub in enumerate(route.partial_routes):
            icon, name, direction = map_type(sub.vehicle)
            message += f"\n`    `{icon} *{name}* _{direction}_" + (
                f" ({sub.duration} min)" if sub.duration is not None else ""
            )
            if sub_idx + 1 < len(route.partial_routes) and sub.stops:
                next = route.partial_routes[sub_idx + 1]
                message += f"\n`    `🔄 `{sub.stops[-1].name}" + (
                    f" ({sub.stops[-1].place})`"
                    if sub.stops[-1].place and sub.stops[-1].place != "Dresden"
                    else "`"
                )
                if next.stops:
                    if next.stops[0].platform:
                        message += f", Steig {next.stops[0].platform.name}"
                    message += f" ({round((next.stops[0].departure - sub.stops[-1].arrival).total_seconds() / 60)} min)"

    return message, kb
    # for route in resp.routes[:min(NUMBER_ROUTES, len(resp.routes))]:


def cb_query_select(update: Update, context: CallbackContext):
    tag, stop, data = get_stop_data(update)
    update.effective_message.edit_reply_markup()

    route = context.chat_data.setdefault("route", {})
    if tag == QueryTag.ROUTE_SELECTED_START:
        route["start"] = stop
    elif tag == QueryTag.ROUTE_SELECTED_DEST:
        route["end"] = stop

    state, kb = QUERY_DEST, None
    message = f"Ok der Start ist `{stop.name}" + (f" ({stop.place})" if stop.place else "") + "`."
    if "end" in route:
        if isinstance(route["end"], Iterable):
            message += " Ich habe mehrere Haltestellen für dein Ziel gefunden, bitte wähle eine."
            kb = keyboard_select_stop(route["end"], QueryTag.ROUTE_SELECTED_DEST)
        else:
            is_typing(update)
            message, kb = routes(route["start"], route["end"])
            state = ConversationHandler.END
    else:
        message += " Schick mir jetzt das Ziel."
    update.effective_message.reply_markdown(
        text=message, quote=True, reply_markup=InlineKeyboardMarkup(kb) if kb else None
    )
    raise DispatcherHandlerStop(state)


def cb_route_stop(update: Update, context: CallbackContext):
    route = context.chat_data.setdefault("route", {})
    is_end = "start" in route and isinstance(route["start"], vvo.Point)

    success, point = handle_stop_message(
        update, QueryTag.ROUTE_SELECTED_DEST if is_end else QueryTag.ROUTE_SELECTED_START
    )
    if not success:
        raise DispatcherHandlerStop(ConversationHandler.END)

    if is_end:
        route["end"] = point
        if isinstance(point, vvo.Point):
            is_typing(update)
            text, kb = routes(route["start"], route["end"])
            update.effective_message.reply_markdown(
                text, reply_markup=InlineKeyboardMarkup(kb), quote=True
            )
            raise DispatcherHandlerStop(ConversationHandler.END)
        raise DispatcherHandlerStop(QUERY_DEST)
    else:
        route["start"] = point
        if isinstance(point, vvo.Point):
            update.effective_message.reply_text(
                "Ok, schick mir jetzt das Ziel (oder einen Standort📍).", quote=True
            )
            raise DispatcherHandlerStop(QUERY_DEST)
        raise DispatcherHandlerStop(QUERY_START)


def cb_route_command(update: Update, context: CallbackContext):
    def error(txt: str):
        update.message.reply_text(txt)
        raise DispatcherHandlerStop(ConversationHandler.END)

    def query(name: str):
        resp = vvo.find_stops(name, shortcuts=True, limit=3)
        if not resp.ok or len(resp.points) == 0:
            error(f"Leider konnte ich keine Haltestelle für `{name}` finden 😔")
        return resp.points

    # Clear old data if re-entered the command conversation
    context.chat_data.setdefault("route", {})

    # If no args, simply echo and next state
    if not context.args:
        update.message.reply_text(
            "Ich suche dir eine Verbindung zwischen zwei Haltestellen.\n"
            "Schick mir jetzt bitte die Erste (oder einen Standort📍).",
            quote=True,
        )
        return QUERY_START

    if len(context.args) != 2:
        start = " ".join(context.args)
        end = None
    else:
        start = context.args[0]
        end = context.args[1]

    start = query(start)
    end = query(end) if end else end
    if end and len(start) == len(end) == 1:
        # Done
        is_typing(update)
        text, kb = routes(start[0], end[0])
        update.effective_message.reply_markdown(
            text, reply_markup=InlineKeyboardMarkup(kb), quote=True
        )
        return ConversationHandler.END
    else:
        route = context.chat_data.setdefault("route", {})
        route["start"] = start
        route["end"] = end

        msg, kb = "", None
        if len(start) == 1:
            route["start"] = start[0]
            msg = f"Ok der Start ist `{start[0].name}`."
            if end:
                msg += " Bitte wähle nun das Ziel aus."
                kb = keyboard_select_stop(end, QueryTag.ROUTE_SELECTED_DEST)
            else:
                msg += " Schick mir jetzt bitte das Ziel (oder einen Standort📍)."
            update.effective_message.reply_markdown(
                msg, reply_markup=InlineKeyboardMarkup(kb), quote=True
            )
            return QUERY_DEST
        elif len(end) == 1:
            route["end"] = end[0]
            msg = f"Ok das Ziel ist `{end[0].name}`. Bitte wähle noch einen Start aus."
            kb = keyboard_select_stop(start, QueryTag.ROUTE_SELECTED_START)
        else:
            msg = "Schick mir jetzt bitte den Start (oder einen Standort📍)."
        update.message.reply_markdown(msg, reply_markup=InlineKeyboardMarkup(kb), quote=True)
        return QUERY_START


def cb_cancel(update: Update, context: CallbackContext):
    context.bot.send_message("Du kannst es gerne später noch mal probieren.")
    return ConversationHandler.END


handler = ConversationHandler(
    entry_points=[CommandHandler("route", callback=cb_route_command)],
    states={
        QUERY_START: [
            MessageHandler(
                Filters.location | (Filters.text & (~Filters.command)), callback=cb_route_stop
            ),
            CallbackQueryHandler(
                callback=cb_query_select,
                pattern=pattern_valid_tag(QueryTag.ROUTE_SELECTED_START, [int]),
            ),
        ],
        QUERY_DEST: [
            MessageHandler(
                Filters.location | (Filters.text & (~Filters.command)), callback=cb_route_stop
            ),
            CallbackQueryHandler(
                callback=cb_query_select,
                pattern=pattern_valid_tag(QueryTag.ROUTE_SELECTED_DEST, [int]),
            ),
        ],
    },
    fallbacks=[CommandHandler("cancel", callback=cb_cancel)],
    allow_reentry=True,
    conversation_timeout=5 * 60,  # 5 Minutes timeout, should be more user friendly
    name="route_handler",
)

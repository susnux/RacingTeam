import vvo

from enum import Enum
from typing import Iterable, Optional, Type, Union
from telegram import Update


class QueryTag(Enum):
    STOP_SELECTED = 1
    STOP_LOCATION = 2
    STOP_FAVORITE = 3

    DEPARTURE_LATER = 10
    DEPARTURE_MORE = 11


def get_data(update: Update) -> tuple[QueryTag, Optional[tuple]]:
    """Get callback data from update"""
    update.callback_query.answer()
    return update.callback_query.data


def get_stop_data(update: Update):
    tag, data = get_data(update)
    response = vvo.find_stops(data[0], shortcuts=True, limit=1)
    if len(response.points) == 0:
        raise RuntimeError(
            "Called with invalid StopID or something went wrong, both should never happen!"
        )
    return tag, response.points[0], tuple(data[1:])


def pattern_valid_tag(
    tag: Union[QueryTag, Iterable[QueryTag]], data_types: list[Union[Type, Iterable[Type]]] = None
):
    """Create a pattern / validator for callback data

    Validates the tag and optionally also the data types
    """
    if isinstance(tag, QueryTag):
        tag = [tag]

    def validator(data):
        valid = (
            isinstance(data, tuple)
            and len(data) == 2
            and isinstance(data[0], QueryTag)
            and data[0] in tag
        )
        if valid and data_types is not None:
            return len(data[1]) == len(data_types) and all(
                [isinstance(data[1][idx], dt) for idx, dt in enumerate(data_types)]
            )
        return valid

    return validator

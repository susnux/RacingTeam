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


def pattern_valid_tag(tag: QueryTag, data_types: list[Union[Type, Iterable[Type]]] = None):
    """Create a pattern / validator for callback data

    Validates the tag and optionally also the data types
    """

    def validator(data):
        valid = (
            isinstance(data, tuple)
            and len(data) == 2
            and isinstance(data[0], QueryTag)
            and data[0] == tag
        )
        if valid and data_types is not None:
            return len(data[1]) == len(data_types) and all(
                [isinstance(data[1][idx], dt) for idx, dt in enumerate(data_types)]
            )
        return valid

    return validator

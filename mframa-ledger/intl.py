"""ISO currency metadata, exact minor units and locale-aware display."""
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, available_timezones
from datetime import datetime
from babel import Locale
from babel.numbers import format_currency, get_currency_precision
from babel.core import get_global

LANGUAGES = {'en': 'English', 'fr': 'Français', 'es': 'Español'}
# CLDR includes historical currencies. Support current tender codes plus major regional/fund units.
from babel.numbers import get_territory_currencies
COUNTRIES = {k:v for k,v in Locale('en').territories.items() if len(k)==2 and k.isalpha() and k.isupper()}
CURRENCIES = sorted({c for territory in COUNTRIES for c in get_territory_currencies(territory)} | {'USD','EUR','GBP','GHS','JPY','KWD','BHD','CLF'})
TIMEZONES = sorted(available_timezones())


def minor_units(value, currency):
    if currency not in CURRENCIES:
        raise ValueError('Unsupported currency.')
    try:
        amount=Decimal(str(value).strip())
        if not amount.is_finite() or amount<0 or amount>100000000:
            raise ValueError('Amount must be between 0 and 100,000,000.')
        scaled=amount * (10**get_currency_precision(currency))
        if scaled != scaled.to_integral_value():
            raise ValueError(f'{currency} supports {get_currency_precision(currency)} decimal places.')
        return int(scaled)
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid monetary amount.')


def major_units(value,currency):
    return Decimal(value)/(10**get_currency_precision(currency))


def money_label(value,currency,language='en'):
    return format_currency(major_units(value,currency),currency,locale=language)


def local_time(timestamp,timezone):
    return datetime.fromisoformat(timestamp.replace('Z','+00:00')).astimezone(ZoneInfo(timezone)).strftime('%Y-%m-%d %H:%M:%S')

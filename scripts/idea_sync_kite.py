import argparse
import asyncio
import functools
import pickle
import os
from utils import google_sheet

import requests
from gspread.utils import numericise_all
from pyppeteer import launch
from requests.cookies import RequestsCookieJar
from datetime import datetime

KITE_URL = "https://kite.zerodha.com"
KITE_API_URL = "https://kite.zerodha.com/api"
ZERODHA_USERID = os.getenv('ZERODHA_USERID')
ZERODHA_PASSWORD = os.getenv("ZERODHA_PASSWORD")
ZERODHA_PIN = os.getenv("ZERODHA_PIN")

INTRADAY_WATCHLIST = "Intraday"
SWING_WATCHLIST = "Swing"
WAITLIST = "Waitlist"
LONG_TERM_IDEAS = "Long term ideas"


def pickle_data(data):
    with open('../auth_data/auth_data_kite.txt', 'wb') as file:
        pickle.dump(data, file)


def load_data():
    # for reading also binary mode is important
    try:
        data = None
        with open('../auth_data/auth_data_kite.txt', 'rb') as file:
            data = pickle.load(file)
        return data
    except:
        return None


def load_cookies(data):
    if not data:
        return None

    jar = RequestsCookieJar()
    if not isinstance(data, list):
        data = [data]

    csrf_token = None
    for c in data:
        name = c.pop('name', None)
        if not name:
            continue

        value = c.pop('value', None)
        c = trim_cookie(c)
        jar.set(name, value, **c)
        if name == 'public_token':
            csrf_token = value
    return jar, csrf_token


def trim_cookie(c):
    c.pop('size', None)
    c.pop('session', None)
    c.pop('httpOnly', None)
    c.pop('sameSite', None)
    return c


async def sentinel_login():
    browser = await launch(headless=True)
    page = await browser.newPage()
    await page.goto(KITE_URL)
    await page.type("#userid", ZERODHA_USERID)
    await page.type("#password", ZERODHA_PASSWORD)
    await page.click("button[type='submit'")
    await page.waitFor(5000)
    await page.type("#pin", ZERODHA_PIN)
    await page.click("button[type='submit'")
    await page.waitForNavigation()
    await page.waitFor(5000)
    cookies = await page.cookies()
    pickle_data(cookies)
    await browser.close()


def authenticate(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        def execute_fun():
            auth_data = load_data()
            if auth_data:
                jar, csrf_token = load_cookies(auth_data)
                resp = f(*args, auth_data=jar, csrf_token=csrf_token, **kwargs)
                return resp
            raise ZeroDivisionError

        try:
            return execute_fun()
        except ZeroDivisionError:
            asyncio.get_event_loop().run_until_complete(sentinel_login())
            return execute_fun()

    return wrapper


def process_response(resp):
    if resp.ok:
        return resp.json()
    if resp.status_code == 403:
        raise ZeroDivisionError


def make_headers(csrf_token=None, cookie_jar=None, **kwargs):
    cookie_header = ""
    if cookie_jar:
        cookies = dict(cookie_jar)
        for k, v in cookies.items():
            cookie_header += f"{k}={v};"
        cookie_header = cookie_header[0: -1]
    return {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15',
        'host': 'kite.zerodha.com',
        'x-kite-version': '2.5.4',
        'x-csrftoken': csrf_token,
        'Cookie': cookie_header,
        **kwargs
    }


@authenticate
def get_watchlists(auth_data=None, csrf_token=None, **kwargs):
    resp = requests.get(f"{KITE_API_URL}/marketwatch", headers=make_headers(csrf_token, auth_data))
    return process_response(resp)


@authenticate
def empty_watchlist(watchlist, auth_data=None, csrf_token=None, **kwargs):
    id = watchlist.get('id')
    status = True
    for item in w.get('items', []):
        resp = requests.delete(f"{KITE_API_URL}/marketwatch/{id}/{item.get('id')}",
                               headers=make_headers(csrf_token, auth_data))
        if not resp.ok:
            status = False

    return status


@authenticate
def add_to_watchlist(watchlist, symbol, auth_data=None, csrf_token=None, **kwargs):
    id = watchlist.get('id')
    data = {
        'segment': 'NSE',
        'tradingsymbol': symbol,
        'watch_id': id,
        'weight': 0
    }
    resp = requests.post(f"{KITE_API_URL}/marketwatch/{id}/items", data=data,
                         headers=make_headers(csrf_token, auth_data))
    if resp.ok:
        return True
    print(resp.text)
    return resp.ok


@authenticate
def create_trigger(symbol, price, op, auth_data=None, csrf_token=None):
    url = f"{KITE_URL}/triggers/new/basic"
    payload = {"rule_name": f"{symbol}-{to_operator_name(op)}-{price}",
               "basket_id": None, "constant_value": round(float(price), 2), "attributeA": "LastTradedPrice",
               "stockA": symbol, "exchangeA": "NSE", "stockB": None, "exchangeB": None, "attributeB": None,
               "operator": op, "rule_constant_compare": True}
    # payload = json.dumps(payload)
    resp = requests.post(url, data=payload, headers={'x-csrftoken': csrf_token}, cookies=auth_data)
    return process_response(resp)


def get_all_records(
        worksheet,
        empty2zero=False,
        head=1,
        default_blank="",
        allow_underscores_in_numeric_literals=False,
        numericise_ignore=None):
    idx = head - 1

    data = worksheet.get_all_values(value_render_option='UNFORMATTED_VALUE')
    worksheet.append_row()
    if len(data) <= idx:
        return []

    keys = data[idx]

    if numericise_ignore == ['all']:
        values = data[idx + 1:]
    else:
        values = [
            numericise_all(
                row,
                empty2zero,
                default_blank,
                allow_underscores_in_numeric_literals,
                numericise_ignore,
            )
            for row in data[idx + 1:]
        ]

    return [dict(zip(keys, row)) for row in values]


def init_parser():
    parser = argparse.ArgumentParser(description='Add to Kite watch list and Ideas log sheet in google.')

    parser.add_argument('--clear', help="Clear watchlist", action='store_true')
    parser.add_argument('--no-sheet', help="Dont sync to google sheet", action='store_true')
    parser.add_argument('--no-alert', help="Dont sync to sentinel", action='store_true')
    parser.add_argument('--no-watch', help="Dont sync to kite watchlist", action='store_true')
    parser.add_argument('--swing', help="If this is to be added in swing watchlist", action='store_true')
    parser.add_argument('--long-term', help="If this is to be added to Long term Ideas", action='store_true')
    parser.add_argument('--waitlist', help="if this is to be added in waitlist", action='store_true')
    parser.add_argument('-s', help="Symbol to add (NSE)")
    parser.add_argument('-type', help='Position type', default='Long')
    parser.add_argument('-e', help='Entry')
    parser.add_argument('-ex', help="Planned exit", default=0)
    parser.add_argument('-sl', help="Stoploss for the trade", default=0)
    return parser


if __name__ == '__main__':
    parser = init_parser()
    args = vars(parser.parse_args())
    if not args['s']:
        raise Exception("Symbol not specified")

    if not args['no_sheet']:
        print("Syncing to google sheet............")
        client, _, _ = google_sheet.init_google_sheet()
        spread_sheet = client.open('Trade Log')
        trade_sheet = spread_sheet.worksheet('Ideas')
        row_num = google_sheet.first_empty_row_based_on_col(trade_sheet, 2)
        trade_sheet.update(f'B{row_num}', [
            [datetime.today().date().isoformat(), None, args['s'], args['type'], args['e'], args['ex'], args['sl']]
        ], raw=False)
        print("Syncing to google sheet done .................")

    if not args['no_watch']:
        print("Getting watchlists from kite...........")
        resp = get_watchlists()
        watchlists = resp.get('data')
        for w in watchlists:
            if w['name'] == INTRADAY_WATCHLIST:
                # this is the watch list we have to delete and add to
                print("Found watchlist..........")
                if args['clear']:
                    print("Clearing watchlist........")
                    status = empty_watchlist(w)
                    if status:
                        print(f"Watchlist {w['name']} is now empty")
                    else:
                        print(f"Watchlist {w['name']} is not successful")

                print(f"Adding to watchlist {w['name']}")
                status = add_to_watchlist(w, args['s'])
                if status:
                    print(f"{args['s']} added successfully")
                else:
                    print(f"{args['s']} cannot be added")

    if not args['no_alert']:
        import sentinal
        resp = sentinal.create_advanced_trigger(args['s'], args['e'], type=args['type'])
        print(f"Sentinel alert created {resp['rule_name']}")

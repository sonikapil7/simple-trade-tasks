import asyncio
import functools
import pickle
import os
from utils import google_sheet
import base64
import json

import requests
from gspread.utils import numericise_all
from pyppeteer import launch
from requests.cookies import RequestsCookieJar

SENTINAL_URL = "https://sentinel.zerodha.com/api"
ZERODHA_USERID = os.getenv('ZERODHA_USERID')
ZERODHA_PASSWORD = os.getenv("ZERODHA_PASSWORD")
ZERODHA_PIN = os.getenv("ZERODHA_PIN")


def pickle_data(data):
    with open('../auth_data/auth_data.txt', 'wb') as file:
        pickle.dump(data, file)


def load_data():
    # for reading also binary mode is important
    try:
        data = None
        with open('../auth_data/auth_data.txt', 'rb') as file:
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
        if name == 'sentinel_csrftoken':
            csrf_token = value
    return jar, csrf_token


def trim_cookie(c):
    c.pop('size', None)
    c.pop('session', None)
    c.pop('httpOnly', None)
    c.pop('sameSite', None)
    return c


async def sentinel_login():
    print("Login with Zerodha")
    browser = await launch()
    page = await browser.newPage()
    await page.goto(f'{SENTINAL_URL}/user/login/kite')
    await page.type("#userid", ZERODHA_USERID)
    await page.type("#password", ZERODHA_PASSWORD)
    await page.click("button[type='submit'")
    await page.waitFor(5000)
    await page.type("#pin", ZERODHA_PIN)
    await page.click("button[type='submit'")
    await page.waitForNavigation()
    await page.waitFor(5000)
    print("Getting auth data from cookies")
    cookies = await page.cookies()
    pickle_data(cookies)
    await browser.close()


def authenticate(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        def execute_fun():
            auth_data = load_data()
            if auth_data:
                print("Trying with existing login information")
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


@authenticate
def get_triggers(auth_data=None, **kwargs):
    resp = requests.get(f"{SENTINAL_URL}/triggers/all", cookies=auth_data)
    return process_response(resp)


def to_operator_name(op):
    ops = {'>': 'gt', '>=': 'gte', '<': 'lt', "<=": 'lte', '==': 'eq'}
    return ops.get(op, 'noop')


@authenticate
def create_trigger(symbol, price, op, auth_data=None, csrf_token=None):
    url = f"{SENTINAL_URL}/triggers/new/basic"
    payload = {"rule_name": f"{symbol}-{to_operator_name(op)}-{price}",
               "basket_id": None, "constant_value": round(float(price), 2), "attributeA": "LastTradedPrice",
               "stockA": symbol, "exchangeA": "NSE", "stockB": None, "exchangeB": None, "attributeB": None,
               "operator": op, "rule_constant_compare": True}
    # payload = json.dumps(payload)
    resp = requests.post(url, data=payload, headers={'x-csrftoken': csrf_token}, cookies=auth_data)
    return process_response(resp)


@authenticate
def create_advanced_trigger(symbol, price, margin=0.003, type="Long", auth_data=None, csrf_token=None):
    url = f"{SENTINAL_URL}/triggers/new/advanced"
    if margin > 0:
        rule = f"Math_Abs(LastTradedPrice('NSE:{str(symbol)}') - {str(price)}) <= (LastTradedPrice('NSE:{str(symbol)}') * {str(margin)})"
        name = f"{symbol}_{type}_{price}_NEAR_ALERT"
    else:
        name = f"{symbol}_{type}_{price}_EQUAL_ALERT"
        rule = f"LastTradedPrice('NSE:{str(symbol)}') == {str(price)}"
    rule_base64 = base64.b64encode(bytes(rule, 'utf-8'))
    payload = {
        "rule_name": name,
        "rule_string": str(rule_base64, 'utf-8'),
        "basket_id": None
    }
    payload = json.dumps(payload)
    resp = requests.post(url, data=payload,
                         headers={'x-csrftoken': csrf_token, "content-type": "application/json",
                                  'Content-transfer-encoding': 'base64'},
                         cookies=auth_data)
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


if __name__ == '__main__':
    client, _, _ = google_sheet.init_google_sheet()
    spread_sheet = client.open('Trade Log')
    ideas_sheet = spread_sheet.worksheet('Ideas')
    ideas = get_all_records(ideas_sheet, head=4, numericise_ignore=['all'])
    ideas = list(filter(lambda x: x['Symbol'] not in ('', '-'), ideas))
    print(f"Found {len(ideas)} ideas")
    for idea in ideas:
        if idea['Symbol']:
            op = '>='
            if idea['Type'] == 'Short':
                op = '<='
            create_trigger(idea['Symbol'], idea['Entry'], op)

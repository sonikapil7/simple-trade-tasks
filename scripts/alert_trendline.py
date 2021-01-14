import argparse
from datetime import datetime as dt

from sympy import Point
from sympy.geometry import Line

import sentinal


def starttime(day, hour, min):
    return (day - 1) * 375 + hour * 60 + min - 555


def print_trigger(s, y1, y2, x2, d, h, m, crossing_below=False):
    line = Line(Point(0, y1), Point(x2, y2))
    print(line.equation())
    x, y, c = line.coefficients
    st = starttime(d, h, m)
    str = f"LastTradedPrice('NSE:{s}') - (({-1 * c} + {-1 * x}*((YearDay() - 1) * 375 + (Math_Min(930, (Hour() * 60 + Minute())) - 555) - {st})) / {y}) {'<' if crossing_below else '>'} 0"

    return str


def init_parser():
    parser = argparse.ArgumentParser(description='Add Trend line Alert')

    parser.add_argument('--clear', help="Clear triggers", action='store_true')
    parser.add_argument('--down', help="Cross Down", action='store_true')

    parser.add_argument('-s', help="Symbol to add (NSE)")
    parser.add_argument("--coords", nargs="+", type=int)
    parser.add_argument("--start", nargs="+", type=int)
    return parser


if __name__ == '__main__':
    parser = init_parser()
    args = vars(parser.parse_args())
    print(args)
    symbol = args['s'].upper()
    y1, y2, x2 = args['coords']
    x1 = 0
    d, h, m = args['start']

    dt.fromtimestamp(x1)
    str = print_trigger(symbol, y1, y2, x2, d, h, m, crossing_below=(args['down']))
    print(str)
    name = f"{symbol}_{'Down' if args['down'] else 'UP'}"
    all_clear = args['clear']
    if all_clear:
        print(f'Clearing Triggers {all_clear}')
        sentinal.clear_triggers(all=all_clear)
    sentinal.create_advanced_trigger_with_rule(str, name=name)

import pandas as pd
import copy
import json
from utils import google_sheet
pos_size = {}
current_position = {}
positions = []


def update_avg_prices_and_quantities(d):
    cp = current_position[d['Instrument']]
    qty = d['Qty.'].split('/')[1]
    avg = d['Avg. price']
    if d['Type'] == 'BUY':
        prev_price = cp['buy_qty'] * cp['buy_price']
        cp['buy_qty'] += int(qty)
        cp['buy_price'] = (prev_price + int(qty) * float(avg))/cp['buy_qty']
    else:
        prev_price = cp['sell_qty'] * cp['sell_price']
        cp['sell_qty'] += int(qty)
        cp['sell_price'] = (prev_price + int(qty) * float(avg)) / cp['sell_qty']


def get_logs_from_csv(file_path):
    data = pd.read_csv(file_path)
    data = data.sort_values('Time', ascending=True)
    for d in data.iloc:
        if pos_size.get(d['Instrument'], 0) == 0:
            pos_size[d['Instrument']] = 0

        if pos_size[d['Instrument']] == 0:
            # this is a first order
            pos_type = 'Long' if d['Type'] == 'BUY' else 'Short'
            new_pos = True
            pos_size[d['Instrument']] = int(d['Qty.'].split('/')[1]) * (1 if d['Type'] == 'BUY' else -1)
            current_position[d['Instrument']] = {
                'date': d['Time'].split(' ')[0],
                'in_time': d['Time'].split(' ')[1],
                'pos_type': pos_type,
                'symbol': d['Instrument'],
                'buy_qty': 0,
                'buy_price': 0,
                'out_time': '',
                'sell_qty': 0,
                'sell_price': 0
            }
            update_avg_prices_and_quantities(d)
        else:
            pos_size[d['Instrument']] += int(d['Qty.'].split('/')[1]) * (1 if d['Type'] == 'BUY' else -1)
            new_pos = False
            update_avg_prices_and_quantities(d)
            if pos_size[d['Instrument']] == 0:
                current_position[d['Instrument']]['out_time'] = d['Time'].split(' ')[1]
                positions.append(copy.deepcopy(current_position[d['Instrument']]))
            current_position[d['Instrument']] = {}


if __name__ == '__main__':
    get_logs_from_csv("orders-2.csv")
    pos = pd.read_json(json.dumps(positions))
    print(pos.to_csv())
    client, _, _ = google_sheet.init_google_sheet()

    spread_sheet = client.open('Trade Log')
    trade_sheet = spread_sheet.worksheet('DT Trades')
    row_num = google_sheet.first_empty_row_based_on_col(trade_sheet, 2)
    trade_sheet.update(f'B{row_num}', [
        [d['date'], d['symbol'], 'Closed',
         d['pos_type'], d['buy_qty'], d['buy_price'],
         None, d['sell_price'], None, d['in_time'], d['out_time']] for d in positions
    ], raw=False)

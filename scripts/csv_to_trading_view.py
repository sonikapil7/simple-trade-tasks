import csv
import sys


with open(sys.argv[1]) as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
    line_count = 0
    symbols = []
    for row in csv_reader:
        if line_count == 0:
            line_count += 1
        else:
            if row and len(row) > 1:
                s = row[0].replace(' ', '').replace('&', '_').replace('-', '_')
                symbols.append(f"NSE:{s}")
    print(",".join(symbols))
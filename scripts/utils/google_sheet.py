from oauth2client.service_account import ServiceAccountCredentials
import gspread
import os

# CRED_FILE_PATH = os.path.abspath('../auth_data/Transport Tracker-a87c7e55a396.json')
CRED_FILE_PATH = os.getenv("CREDENTIAL_JSON_PATH")


def init_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']

    creds = ServiceAccountCredentials.from_json_keyfile_name(CRED_FILE_PATH, scope)
    client = gspread.authorize(creds)

    return client, creds, scope


def first_empty_row_based_on_col(sheet, col_index):
    all = sheet.col_values(col_index)
    row_num = 1
    consecutive = 0
    for col in all:
        flag = False
        if col not in ("", '-', None):
            # something is there!
            flag = True

        if flag:
            consecutive = 0
        else:
            # empty row
            consecutive += 1

        if consecutive == 2:
            # two consecutive empty rows
            return row_num - 1
        row_num += 1
    return row_num


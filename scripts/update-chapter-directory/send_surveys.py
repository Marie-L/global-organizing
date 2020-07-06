#!/usr/bin/env python
#  -*- coding: utf-8 -*-

"""
Script to update PyLadies Chapter Directory.

To use you'll need to have a Google Project with a Service Account
- see: https://support.google.com/a/answer/7378726?hl=en - and download the client credentials for
the Service Account.

Additionally you'll need to set a `.env` file with the following to send the chapter survey emails:
- GMAIL_ACCOUNT_NAME
- GMAIL_ACCOUNT_PASSWORD
- GOOGLE_CREDENTIALS_FILE

You can run from the commandline with: send_surveys.py
"""
from os import getenv
from os.path import join, dirname

from dotenv import load_dotenv

__author__ = "Lorena Mesa"
__email__ = "lorena@pyladies.com"

from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import gspread
from gspread import SpreadsheetNotFound, Cell
from oauth2client.service_account import ServiceAccountCredentials

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Setup Gmail Account and Google variables
GMAIL_ACCOUNT_NAME = getenv('GMAIL_ACCOUNT_NAME')
GMAIL_ACCOUNT_PASSWORD = getenv('GMAIL_ACCOUNT_PASSWORD')
GOOGLE_CREDENTIALS_FILE = getenv('GOOGLE_CREDENTIALS_FILE')


class GoogleSheetsAPI(object):
    def __init__(self, scope, credentials_file):
        self.scope = scope
        self.credentials_file = credentials_file

    def get_client(self):
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, self.scope)
        self.client = gspread.authorize(creds)

    def _get_sheet(self, sheet):
        return self.client.open(sheet)

    def get_worksheet_by_title(self, sheet, worksheet_title):
        try:
            sheet = self._get_sheet(sheet)
        except SpreadsheetNotFound:
            raise SpreadsheetNotFound

        worksheet = list(filter(lambda sheet: sheet.title == worksheet_title, sheet.worksheets()))

        if len(worksheet):
            return worksheet[0]
        else:
            return None


def update_pyladies_list(gsheets_api, directory_name, last_download_sheet, tracker_sheet):
    try:
        last_download = gsheets_api.get_worksheet_by_title(
            sheet=directory_name, worksheet_title=last_download_sheet
        )
    except SpreadsheetNotFound:
        print(f'Download sheet: {last_download_sheet} not found')
        return False

    tracker = gsheets_api.get_worksheet_by_title(
        sheet=directory_name, worksheet_title=tracker_sheet
    )

    if not last_download:
        print("No latest data, skipping PyLadies list update ...")
        return False

    last_download_data = last_download.get_all_records()
    tracker_data = tracker.get_all_records()

    existing_pyladies_emails = list(map(
        lambda record: record.get('Email Address [Required]'),
        tracker_data
    ))

    header = tracker.row_values(1)
    new_pyladies = list(filter(
        lambda record: record.get('Email Address [Required]') not in existing_pyladies_emails,
        last_download_data
    ))
    new_pyladies += tracker_data
    new_pyladies = sorted(new_pyladies, key=lambda record: record.get('First Name [Required]'))

    cells_to_update = list(map(lambda col_name: Cell(row=1, col=header.index(col_name)+1, value=col_name), header))

    for indx, record in enumerate(new_pyladies):

        if not record.get('First Name [Required]'):
            continue

        for h_indx, col in enumerate(header):
            cells_to_update.append(
                Cell(row=indx+2,                          # Row aren't 0 based, Row 1 is the header
                     col=h_indx+1,                          # Col aren't 0 based like an index :-)
                     value=record.get(col))
            )
    tracker.clear()
    tracker.update_cells(cells_to_update)
    return True


def get_pyladies_emails_for_survey(gsheets_api, directory_name, tracker_sheet, chapter_directory_sheet):
    tracker = gsheets_api.get_worksheet_by_title(
        sheet=directory_name, worksheet_title=tracker_sheet
    )
    tracker_data = tracker.get_all_records()

    chapter_directory = gsheets_api.get_worksheet_by_title(
        sheet=directory_name, worksheet_title=chapter_directory_sheet
    )
    chapter_directory_data = chapter_directory.get_all_records()
    chapter_directory_emails = list(map(
        lambda record: record.get('What is your PyLadies official email?'),
        chapter_directory_data
    ))

    cells_to_update, users_to_email = [], []
    header = tracker.row_values(1)
    chapter_directory_indx = header.index('Chapter Directory')
    for indx, record in enumerate(tracker_data):
        email = record.get('Email Address [Required]')
        if email in chapter_directory_emails:
            record['Chapter Directory'] = 'YES'
        else:
            record['Chapter Directory'] = 'NO'
            users_to_email.append(record)
        cells_to_update.append(
            Cell(row=indx+2,                                # Row aren't 0 based, Row 1 is the header
                 col=chapter_directory_indx+1,              # Col aren't 0 based like an index :-)
                 value=record.get('Chapter Directory'))
        )
        print(f'Done with {indx}')

    tracker.update_cells(cells_to_update)
    return users_to_email


def create_prefilled_surveys(users_to_email, directory_name, email_sheet_name):
    # Use form_url and inspect with dev tools to update these for the questions, if needed
    form_items = [
        'entry.1005228805', 'entry.1845393520', 'entry.628679392', 'entry.1350360094',
        'entry.525776572', 'entry.1794068471', 'entry.1755579263', 'entry.305825898',
        'entry.1016984817'
    ]
    # This survey form url shouldn't change, but if so ask PyLadies Global Team
    form_url = 'https://docs.google.com/forms/d/e/1FAIpQLSf43R4FbiIE4z76k5z42UU4HKMKJnTr2ldh4KecE4WRTJZLUw/viewform?'

    email_sheet = gsheets_api.get_worksheet_by_title(
        sheet=directory_name, worksheet_title=email_sheet_name
    )
    email_sheet.clear()

    # Instantiate header for email survey sheet
    today_string = datetime.now().strftime('%Y-%m-%d')
    email_cells = [
        Cell(row=1, col=1, value='Chapter Email'),
        Cell(row=1, col=2, value='Survey URL'),
        Cell(row=1, col=3, value=f'{today_string} Email Sent')
    ]
    emails_to_send = []
    for indx, user in enumerate(users_to_email):
        email_address = user.get("Email Address [Required]")
        recipient = f'{user.get("First Name [Required]")} {user.get("Last Name [Required]")}'
        query_params = {
            form_items[0]: recipient,
            form_items[1]: email_address,
            form_items[2]: f'{user.get("First Name [Required]")}' if not user.get('city') else f'{user.get("City")}',
            form_items[3]: f'{user.get("Country")}',
            form_items[4]: f'{user.get("Organizer")}',
            form_items[5]: f'{user.get("Organizer Email")}',
            form_items[6]: f'{user.get("Chapter Language")}',
            form_items[7]: f'{user.get("Chapter MeetUp Website")}',
            form_items[8]: f'{user.get("Chapter Website")}'
        }
        query_string = urlencode(query_params)
        survey_url = f'{form_url}{query_string}'
        emails_to_send.append(
            {
                'email_address': email_address,
                'recipient': recipient,
                'survey_url': survey_url
            }
        )
        # Add each cell in: email, survey link, email sent
        email_cells.append(
            Cell(row=indx + 2,          # Row aren't 0 based, Row 1 is the header
            col=1,                 # Col aren't 0 based like an index :-)
            value=email_address)
        )
        email_cells.append(
            Cell(row=indx + 2,          # Row aren't 0 based, Row 1 is the header
            col=2,                 # Col aren't 0 based like an index :-)
            value=survey_url)
        )
        email_cells.append(
            Cell(row=indx + 2,          # Row aren't 0 based, Row 1 is the header
            col=3,                 # Col aren't 0 based like an index :-)
            value='NO')
        )

    email_sheet.update_cells(email_cells)
    return emails_to_send


def send_emails(emails, gmail_user, gmail_password, directory_name, email_sheet_name):
    email_sheet = gsheets_api.get_worksheet_by_title(
        sheet=directory_name, worksheet_title=email_sheet_name
    )
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
    except Exception as e:
        print(e)
        print(f'Unable to login into {gmail_user} account, cancelling emails...')
        return False
    email_cells = []
    for indx, email in enumerate(emails):
        print(email.get('email_address'))
        email_address = email.get('email_address')

        message = MIMEMultipart()
        message['to'] = email_address
        message['from'] = gmail_user
        message['subject'] = '[IMPORTANT] We need your PyLadies Chapter ' \
                             'Information for the PyLadies Chapter Directory for voting'

        message_text = f'Dear {email.get("recipient")},\n\nPlease review and complete your PyLadies Chapter ' \
                       f'information for the PyLadies Chapter Directory: {email.get("survey_url")}.\n\nWe are ' \
                       f'using this to update the PyLadies map found on pyladies.com. Additionally your chapter ' \
                       f'directory information will be used for the forthcoming vote for selecting the PyLadies' \
                       f'Global Council selection process (https://github.com/pyladies/global-organizing/issues/50). ' \
                       f'A forthcoming email  will be additionally sent detailing this process.' \
                       f'\n\nIf you have any questions you can email info@pyladies.com.\n\nThanks!\n\nLorena Mesa on ' \
                       f'behalf of the PyLadies Global Team'

        msg = MIMEText(message_text)
        message.attach(msg)

        try:
            server.sendmail(from_addr=gmail_user, to_addrs="lorena@pyladies.com", msg=message.as_string())
            print(f'Sent message successfully: {email_address}')
            # email_cells.append(
            #     Cell(row=indx + 2,  # Row aren't 0 based, Row 1 is the header
            #          col=3,  # Col aren't 0 based like an index :-)
            #          value='YES')
            # )
        except Exception as e:
            print(f'An error occurred while trying to send email for {email_address}: {e}')

    email_sheet.update_cells(email_cells)
    return True


if __name__ == "__main__":
    print('Starting script ...')

    # Set names for worksheets
    directory_name = 'PyLadies Chapter Directory'
    tracker_sheet = 'last_download'
    chapter_directory_sheet = 'PyLadies Chapter Directory Form Resp - Nov 2019'
    email_sheet = 'PyLadies Survey Emails'
    # Update below with the latest download sheet pulled
    last_download_sheet = input('What is the name of your latest download sheet (e.g. download_nov_21_2019)?')

    gsheets_api = GoogleSheetsAPI(
        scope=[
            'https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'
        ],
        credentials_file=GOOGLE_CREDENTIALS_FILE
    )
    gsheets_api.get_client()

    updated_list = update_pyladies_list(gsheets_api, directory_name, last_download_sheet, tracker_sheet)
    if updated_list:
        print(f'Updated PyLadies List with {last_download_sheet}.')

    users_to_email = get_pyladies_emails_for_survey(
        gsheets_api, directory_name, tracker_sheet, chapter_directory_sheet
    )
    emails_to_send = create_prefilled_surveys(users_to_email, directory_name, email_sheet)
    send_emails(emails_to_send, GMAIL_ACCOUNT_NAME, GMAIL_ACCOUNT_PASSWORD, directory_name, email_sheet)

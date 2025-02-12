import asyncio
import aiohttp
import ssl
import certifi
import pandas as pd
import random
import logging
import argparse
import os
from dotenv import load_dotenv
from user_agent_generator import generate_unique_uas
from datetime import datetime, timedelta, date
from dateutil import parser


load_dotenv()

logging.basicConfig(
    level=logging.INFO,                    # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Format of the log messages
    handlers=[                              # Define where to output logs
        logging.FileHandler('historic_fx.log'),     # Log to a file
        logging.StreamHandler()             # Log to console (standard output)
    ]
)


def parse_date(date_input) -> datetime:
    """ This function takes a date in whatever string format and returns a datetime object. """

    if isinstance(date_input, datetime):
        return date_input  # Return directly if already a datetime object

    if isinstance(date_input, str):
        try:
            # Example of explicit known formats for better performance
            known_formats = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y"]

            for fmt in known_formats:
                try:
                    return datetime.strptime(date_input, fmt)
                except ValueError:
                    continue  # Try the next format

            # If none of the known formats match, fallback to dateutil parser
            return parser.parse(date_input)

        except (ValueError, TypeError) as e:
            logging.error(f"Error parsing date string: {date_input} - {e}")
            raise ValueError("Invalid date format provided.") from e

    raise TypeError("Input must be a string or datetime object.")


def parse_source(file_path, base_list, quote_list, date_list):
    """
    Accepts a file (csv, xlsx) or lists. If a file is passed, each row is returned as an iterable.
    If lists are passed, the number of iterables generated is x*y*z where x, y, and z are the lengths
    of the provided lists, respectively.
    """
    try:
        if not file_path or not (base_list and quote_list and date_list):
            raise ValueError("Either a file path or all three lists must be provided.")

        elif file_path:
            file_extension = file_path.split('.')[-1].lower()
            if file_extension in ['csv', 'xlsx']:
                read_func = pd.read_csv if file_extension == 'csv' else pd.read_excel
                df = read_func(file_path, header=None)
                df = df.dropna(how='all')
                df[2] = df[2].apply(parse_date)
                return [tuple(row) for row in df.itertuples(index=False)]
            else:
                logging.error("Unsupported file type provided.")
        else:
            formatted_dates = [parse_date(d) for d in date_list]
            return [(b, q, d) for d in formatted_dates for b in base_list for q in quote_list]
    except Exception as e:
        logging.error(f"Error processing data: {e}")


async def parse_fx_pair(session, semaphore, b_cur, q_cur, fx_date, user_agent, proxies):

    """ A single task that parses a currency pair exchange rate for a given date """

    # variables below are sent to api
    start_date = fx_date - timedelta(days=1)
    start_date_str = datetime.strftime(start_date, "%Y-%m-%d")
    end_date_str = datetime.strftime(fx_date, "%Y-%m-%d")
    try:
        async with semaphore:
            api = f"https://fxds-public-exchange-rates-api.oanda.com/cc-api/currencies?base={b_cur}&quote={q_cur}&data_type=general_currency_pair&start_date={start_date_str}&end_date={end_date_str}"
            async with session.get(api, headers={"User-Agent": random.choice(user_agent)},
                                   proxy=proxies) as response:
                json_data = await response.json()
                bid_rate = float(json_data["response"][0]["average_bid"])
                ask_rate = float(json_data["response"][0]["average_ask"])
                mid_rate = (bid_rate + ask_rate) / 2
                row = {"Base_currency": b_cur, "Quote_currency": q_cur, "Exchange_rate": mid_rate, "Date": fx_date}
                return row

    except Exception as e:
        logging.error(f"Fetching an exchange rate {b_cur}/{q_cur} on {end_date_str}: {e}")


async def main(source, base, quote, fx_date):
    """ Parses required currency pairs from the source to obtain exchange rates and store them into a table """

    timestamp = datetime.now()
    print(f"Session created on {timestamp}")
    cert_path = certifi.where()
    ssl_context = ssl.create_default_context(cafile=cert_path)
    conn = aiohttp.TCPConnector(ssl=ssl_context)
    custom_headers = generate_unique_uas()
    rows = parse_source(source, base, quote, fx_date)
    # iterate over a list of base currencies and parse exchange rates
    try:
        async with aiohttp.ClientSession(connector=conn) as session:
            semaphore = asyncio.Semaphore(1000)
            tasks = [parse_fx_pair(session, semaphore, row[0], row[1], row[2],
                                   random.choice(custom_headers), DEFAULT_PROXIES) for row in rows]
            results = await asyncio.gather(*tasks)
            clean_results = [r for r in results if r is not None or isinstance(r, dict)]
    except asyncio.TimeoutError as e:
        logging.error(f"The event loop failed due to {e}")
    # return dataframe
    df = pd.DataFrame(clean_results)
    cwd = os.getcwd()
    output_file = os.path.join(cwd, f"output{date.today()}.xlsx")
    with pd.ExcelWriter(output_file, mode='w') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False)
        logging.info("The output file has been created.")
    print(f"Elapsed time in seconds: {(datetime.now() - timestamp).total_seconds()}")
    print(f"The product file was created in the specified folder")


DEFAULT_PROXIES = os.getenv("PROXY")
SOURCE_FILE = None
BASE_CURRENCIES = ["USD", "EUR", "HRK", "GBP"]
QUOTE_CURRENCIES = ["JPY", "AUD", "HKD", "CAD"]
DATES = ["2024-12-13", "2024-12-14", "2025-01-09", "2025-01-11"]

p = argparse.ArgumentParser()
p.add_argument("-s", "--source_file", type=str, default=SOURCE_FILE,
               help="file with requested currency pairs")
p.add_argument("-b", "--base_currencies", nargs="+", type=str, default=BASE_CURRENCIES,
               help="list of base currencies")
p.add_argument("-q", "--quote_currencies", nargs="+", type=str, default=QUOTE_CURRENCIES,
               help="list of quote currencies")
p.add_argument("-d", "--dates", type=str, default=DATES,
               help="dates to be parsed")

args = p.parse_args()

asyncio.run(main(args.source_file, args.base_currencies, args.quote_currencies, args.dates))

import requests
import asyncio
import aiohttp
import ssl
import certifi
import pandas as pd
import random
import logging
import argparse
import os
import sys
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from user_agent_generator import generate_unique_uas

load_dotenv()

logging.basicConfig(
    level=logging.INFO,                    # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Format of the log messages
    handlers=[                              # Define where to output logs
        logging.FileHandler('historic_fx.log'),     # Log to a file
        logging.StreamHandler()             # Log to console (standard output)
    ]
)


def timestamp_ms_to_date(timestamp_ms):
    """ Converts timestamp in milliseconds into a date. """

    # Convert milliseconds to seconds
    timestamp_seconds = timestamp_ms / 1000
    # Convert Unix timestamp to datetime
    return datetime.fromtimestamp(timestamp_seconds)


async def transform_df(json, transformation_function):
    """ Creates a table. """

    df = pd.json_normalize(json['widget'])
    selected_columns = ['baseCurrency', 'quoteCurrency', 'data']
    df = df[selected_columns]
    df = df.explode('data').dropna()
    df[['timestamp', 'exchange_rate']] = pd.DataFrame(df['data'].tolist(), index=df.index)
    df = df.drop(columns='data')
    df.columns = ['Base_currency', 'Quote_currency', 'Date', 'Exchange_rate']
    df = df[["Base_currency", "Quote_currency", "Exchange_rate", "Date"]]
    df["Date"] = df["Date"].apply(lambda x: transformation_function(x))
    return df


async def parse_exchange_rates(session, base_currency, quotes, start_date, end_date, semaphore, user_agent, proxies):
    """ Takes a base currency and up to 10 quote currencies.
    For each pair retrieves exchange rates and stores them into a table. """

    df = None
    try:
        async with semaphore:
            # if more than 10 quotes are passed, excessive elements are ignored,
            # whereas if sub-maximal, the list is padded with "" for each missing
            quotes = quotes[:10] + [""] * (10 - len(quotes))
            quote_0, quote_1, quote_2, quote_3, quote_4, quote_5, quote_6, quote_7, quote_8, quote_9 = quotes

            # call api with widget
            widget = f"https://fxds-hcc.oanda.com/api/data/update/?&source=OANDA&adjustment=0&base_currency={base_currency}&start_date={start_date}&end_date={end_date}&period=daily&price=mid&view=table&quote_currency_0={quote_0}&quote_currency_1={quote_1}&quote_currency_2={quote_2}&quote_currency_3={quote_3}&quote_currency_4={quote_4}&quote_currency_5={quote_5}&quote_currency_6={quote_6}&quote_currency_7={quote_7}&quote_currency_8={quote_8}&quote_currency_9={quote_9}"
            async with session.get(widget, headers={"User-Agent": random.choice(user_agent)},
                                   proxy=proxies) as response:
                json_data = await response.json()
                # model data and return a table with exchange rates
                df = await transform_df(json_data, timestamp_ms_to_date)
    except aiohttp.ClientError as e:
        logging.error(f"Parsing {base_currency} failed due to client-side error: {e}")
    except aiohttp.ContentTypeError as e:
        logging.error(f"Unable to retrieve json file for {base_currency} due to: {e}")
    except KeyError as e:
        logging.error(f"json file was retrieved but the parsing of {base_currency} failed due to: {e}")
    return df


async def main(base_cur, quote_cur, number_days, proxies, fpath=None, fname=None):
    """ Given base currencies, quote currencies and day period inputs,
    it iterates over base-quote pairs and retrieves exchange rates.
        If there are no currencies to shortlist, it will iterate over all of them. """

    timestamp = datetime.now()
    print(f"Session created on {timestamp}")

    cert_path=certifi.where()
    ssl_context = ssl.create_default_context(cafile=cert_path)
    conn = aiohttp.TCPConnector(ssl=ssl_context)

    # define period from-to and convert it to string in specific format
    # months and days must not be zero-padded
    date_format = "%Y-%m-%d"
    end_date = timestamp.date()
    start_date = end_date - timedelta(days=number_days)
    start_date = datetime.strftime(start_date, date_format)
    end_date = datetime.strftime(end_date, date_format)

    custom_headers = generate_unique_uas()

    # retrieve currency list from first api call
    try:
        api = f"https://fxds-hcc.oanda.com/api/initialize?source=OANDA&adjustment=0&base_currency=USD&start_date={start_date}&end_date={end_date}&period=daily&price=bid&view=graph&quote_currency_0=EUR&quote_currency_1=&quote_currency_2=&quote_currency_3=&quote_currency_4=&quote_currency_5=&quote_currency_6=&quote_currency_7=&quote_currency_8=&quote_currency_9=&_=1705073839908"
        response = requests.get(api, headers={"User-Agent": random.choice(custom_headers)},
                                proxies={"http": proxies}, verify=cert_path)
        json_data = response.json()
        currency_list = [c["value"] for c in json_data["currency_list"] if "value" in c]
    except requests.ConnectionError:
        logging.error(f"Unable to retrieve the list of currencies due to faulty connection, session stops immediately")
        sys.exit(1)
    except requests.JSONDecodeError:
        logging.error(f"Unable to retrieve the list of currencies because json was not decoded, session stops immediately")
        sys.exit(1)
    # currencies are shortlisted depending on the input
    if len(base_cur) > 0:
        shortlisted_currencies = list(set(base_cur) & set(currency_list))
        shortlisted_currencies.sort()
    else:
        shortlisted_currencies = currency_list

    # iterate over a list of base currencies and parse exchange rates
    try:
        async with aiohttp.ClientSession(connector=conn) as session:
            semaphore = asyncio.Semaphore(20)
            tasks = [parse_exchange_rates(session, base_currency, quote_cur, start_date, end_date, semaphore,
                                          custom_headers, DEFAULT_PROXY) for
                     base_currency in shortlisted_currencies]
            results = await asyncio.gather(*tasks)
    except asyncio.TimeoutError as e:
        logging.error(f"The event loop failed due to {e}")

    fx = pd.concat(results, ignore_index=True)
    folder = os.getcwd() if fpath is None else fpath
    file_name = "product" if fname is None else fname
    file_path = os.path.join(folder, file_name)
    timestamp_path = f"{file_path}_{str(date.today())}.xlsx"
    with pd.ExcelWriter(timestamp_path, mode='w') as writer:
        fx.to_excel(writer, sheet_name='Sheet1', index=False)
    print(f"Elapsed time in seconds: {(datetime.now() - timestamp).total_seconds()}")
    print(f"The product file was created in the specified folder")


DEFAULT_PROXY = os.getenv("PROXY")
currencies = []
quote_currencies = ["USD", "EUR", "GBP", "CHF", "AUD", "CAD", "JPY", "CNY", "HKD", "SGD"]
days = 180

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--base_currencies", nargs="+", type=str, default=currencies,
                    help="list of base currencies")
parser.add_argument("-q", "--quote_currencies", nargs="+", type=str, default=quote_currencies,
                    help="list of quote currencies")
parser.add_argument("-d", "--number_days", type=int, default=days, help="number of last n days")
parser.add_argument("-n", "--file_name", type=str, default=None, help="alternative file name")
parser.add_argument("-f", "--file_path", type=str, default=None, help="alternative file path")
parser.add_argument("-p", "--proxies", type=str, default=DEFAULT_PROXY,
                    help="rotating proxies")

args = parser.parse_args()

asyncio.run(main(args.base_currencies, args.quote_currencies, args.number_days, args.proxies))

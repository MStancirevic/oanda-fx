Functions are used to retrieve FX pairs from OANDA's unofficial API.

The function **oanda_fx.py** retrieves any currency exchange pair for any date. It uses an asynchronous event loop and rotating proxies to parse multiple tasks concurrently.
It returns the mid exchange rate  that is calculated from the avaialble data.
The function accepts the following inputs:

- proxies
- a file with base currencies (ISO 3-letter code name), quote currencies (ISO 3-letter code name) and dates, each stored in its own column. Each row represents a single task.
- alternatively, if the file is not passed, three lists must be passed as separate inputs: base currencies, quote currencies, and dates. This approach changes iterating logic, the number of tasks created
  equals d * b * q, where d, b, and q denotes the number of dates, number of base currencies and number of quote currencies, respectively.

The function returns the output in XLSX.

The function **oanda_fx_hist.py** is used to retrieve data in bulk for up to 180 days retard (the maximum allowed using an unofficial API). It uses an asynchronous event loop and rotating proxies to parse multiple tasks concurrently.
The function accepts the following inputs:

- base currencies (a list of ISO 3-letter code names)
- quote currenicies (a list of up to 10 ISO 3-letter code name). The number of tasks equals b, where b is the number of base currencies, which means that for each base currency, the
  function will return conversions to all quote currencies specified for the number of dates specified.
- the number of dates as integer
- proxies
- alternative output folder (optional)
- alternative file name (optional)

The function returns the output in XLSX.

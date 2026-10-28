# Market Price Tracker
![tests](https://github.com/nsajjuphilip3-pixel/market-price-tracker/actions/workflows/tests.yml/badge.svg)

A shared price board so farmers and buyers can see what produce sells for in each market.



## Features
- Crowd-sourced price reports from many markets
- Median prices over the last 7 days, resistant to typing mistakes
- Outlier detection and week-on-week trend
- Compare markets for each commodity
- Works offline: no internet and no extra packages needed

## Requirements
- Python 3.8 or newer ([python.org](https://www.python.org))

## Run it

```bash
python app.py
```

Then open <http://127.0.0.1:8000> in your browser.

To share it on your Wi-Fi or phone hotspot (people on the same network can then open it):

```bash
python app.py --host 0.0.0.0
```

## Run the tests

```bash
python -m unittest discover -s tests
```

## How it was built

See [TUTORIAL.md](TUTORIAL.md) for the step-by-step guide. It uses a small shared toolkit, `minikit.py`, explained in [MINIKIT-GUIDE.md](MINIKIT-GUIDE.md).

## Data

Sample data is for demonstration only. Replace it with verified local data. The database file (`*.db`) is created on your computer, is excluded by `.gitignore`, and no personal data is stored in this repository.

## Note

Sample markets and units are included for demonstration. The app is only useful when real people report real prices.

## Contributing

Ideas and fixes are welcome. Open an Issue or a Pull Request. Please never include real personal data.

## Licence

MIT. See [LICENSE](LICENSE).

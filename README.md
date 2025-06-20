# SEO Parser

Simple SEO crawler with PyQt5 interface.

## Requirements
- Python 3.10+
- PyQt5
- aiohttp
- beautifulsoup4
- pandas
- openpyxl

## System Packages for PyQt5 on Linux
PyQt5 depends on system libraries that may not be installed by default on Linux.
Install them with `apt`:

```bash
sudo apt-get update
sudo apt-get install libgl1
```

If `libGL.so.1` is missing, the GUI will fail to start until the package above is
installed.

## Usage
Install requirements:
```bash
pip install -r requirements.txt
```

Run application:
```bash
python -m seoparser
```

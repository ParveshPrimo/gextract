# Google Maps Business Information Extractor

A local productivity tool built with **Streamlit** and **Playwright** that automates the collection of publicly visible business information from Google Maps.

## Features

- **Modern Dashboard**: Built with Streamlit for a simple, responsive control panel and detailed progress feedback.
- **Dynamic Scrolling**: Scans Google Maps search results lists and gathers links.
- **Comprehensive Details Extraction**: Opens listings to parse Name, Category, Ratings, Reviews Count, Phone, Website, Address, Location Coordinates, and Opening Hours.
- **Robust Error Handling**: Uses intelligent fallbacks and skip-on-failure design so that if a single listing is problematic, the rest continue.
- **Incremental SQLite Storage**: Saves results page-by-page to a local SQLite database to prevent data loss.
- **Job History**: Review previous extraction runs, inspect details previews, and export them.
- **Excel & CSV Export**: Download results in CSV or Excel spreadsheets instantly.
- **Headless Toggle**: Toggle headless browser execution to watch the automated process in real-time or run in the background.

---

## Technical Stack

- **Python 3.12+**
- **Streamlit** (UI Dashboard)
- **Playwright** (Chromium browser automation)
- **Pandas** & **OpenPyXL** (Spreadsheet generation)
- **SQLite** (History tracking & local storage)

---

## Folder Structure

```
google_maps_extractor/
│── app.py            # Streamlit Main App
│── scraper.py        # Playwright Scraper logic
│── exporter.py       # DB to CSV/Excel exporter
│── models.py         # Business details data models
│── database.py       # SQLite connection & transactions
│── utils.py          # Paths, Directories, and Loggers setup
│── requirements.txt  # Python Dependencies list
│── README.md         # Documentation & Setup guide
│
├── downloads/        # Generated spreadsheets (.csv & .xlsx)
├── logs/             # App logs and job logs (.log)
├── screenshots/      # Screenshots directory
└── database/         # SQLite DB file storage
```

---

## Setup and Installation

### 1. Set up a Python Virtual Environment
We recommend using a Python virtual environment to manage dependencies locally.

```bash
# Navigate to the workspace folder
cd /home/parvesh/Documents/gex

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

### 2. Install Python Dependencies
```bash
pip install -r google_maps_extractor/requirements.txt
```

### 3. Install Playwright Web Browser Binaries
Playwright requires browser binaries to control Chromium. Run the following command to download them:

```bash
playwright install chromium
```

---

## Running the Application

Once setup is complete, run the Streamlit dashboard using:

```bash
streamlit run google_maps_extractor/app.py
```

Streamlit will print a URL (usually `http://localhost:8501`) that you can open in your web browser.

---

## Usage Guide

1. **Enter Search Query**: Input search phrases like `"Dentists in Seattle"`, `"Coffee shops in Boston"`, or `"Libraries in London"`.
2. **Set Limit**: Choose the maximum number of businesses you want to retrieve.
3. **Format**: Select your preferred export spreadsheet format (CSV or Excel).
4. **Browser Mode**: Toggle **Headless Mode** checkbox. If unchecked, a Chromium window will launch on your screen, allowing you to watch the scraper navigate.
5. **Start Extraction**: Click **Start** to run. You will see progress counters, active ETA calculations, live scrolling logs, and a data grid updating in real-time.
6. **Export**: Once the run completes (or you click **Stop**), select the job from the **Previous Extraction Runs** dropdown, select your export format, and click **Download** to save your spreadsheet.

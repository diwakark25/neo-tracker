# 🚀 NEO Tracker

NEO Tracker is a Python application that fetches data from NASA's Near-Earth Object (NEO) API, stores it in a local SQLite database, and provides insights through console output and visualizations.

![NEO Chart](https://upload.wikimedia.org/wikipedia/commons/7/71/NEO_orbit.gif)

---

## 📌 Features

- Pulls real-time NEO data from NASA's public API
- Saves asteroid data including name, size, speed, miss distance, and hazard status to SQLite
- Displays the top 5 most hazardous near-Earth objects
- Plots a daily count of NEOs for the past 5 days

---

## 🛠️ Requirements

Install dependencies with:

```bash
pip install requests pandas matplotlib pandas requests

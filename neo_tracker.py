import requests
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


API_KEY = 'DEMO_KEY' 
DB_NAME = 'neo_data.db'
START_DATE = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')


def fetch_neo_data(start_date, end_date, api_key):
    print("Fetching data from NASA API...")
    url = f'https://api.nasa.gov/neo/rest/v1/feed?start_date={start_date}&end_date={end_date}&api_key={api_key}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch data:", response.status_code)
        return None

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS neos (
        id TEXT PRIMARY KEY,
        name TEXT,
        date TEXT,
        diameter REAL,
        speed REAL,
        miss_distance REAL,
        is_hazardous BOOLEAN
    )
    ''')
    conn.commit()
    return conn

def insert_data(conn, data):
    print("Inserting data into database...")
    cursor = conn.cursor()
    for date in data['near_earth_objects']:
        for obj in data['near_earth_objects'][date]:
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO neos (id, name, date, diameter, speed, miss_distance, is_hazardous)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    obj['id'],
                    obj['name'],
                    obj['close_approach_data'][0]['close_approach_date'],
                    obj['estimated_diameter']['meters']['estimated_diameter_max'],
                    float(obj['close_approach_data'][0]['relative_velocity']['kilometers_per_hour']),
                    float(obj['close_approach_data'][0]['miss_distance']['kilometers']),
                    int(obj['is_potentially_hazardous_asteroid'])
                ))
            except Exception as e:
                print("Error inserting record:", e)
    conn.commit()

def show_top_dangerous_asteroids(conn):
    print("\nTop 5 Potentially Hazardous NEOs:")
    query = '''
    SELECT name, diameter, speed, miss_distance FROM neos
    WHERE is_hazardous = 1
    ORDER BY diameter DESC
    LIMIT 5;
    '''
    df = pd.read_sql_query(query, conn)
    print(df)

def plot_neo_counts(conn):
    print("\nPlotting NEOs count per day...")
    query = '''
    SELECT date, COUNT(*) as count FROM neos GROUP BY date ORDER BY date;
    '''
    df = pd.read_sql_query(query, conn)
    plt.figure(figsize=(10, 5))
    plt.plot(df['date'], df['count'], marker='o', color='blue')
    plt.title('NEO Counts Per Day')
    plt.xlabel('Date')
    plt.ylabel('Number of NEOs')
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def main():
    data = fetch_neo_data(START_DATE, END_DATE, API_KEY)
    if data:
        conn = setup_database()
        insert_data(conn, data)
        show_top_dangerous_asteroids(conn)
        plot_neo_counts(conn)
        conn.close()
    else:
        print("No data to process.")

if __name__ == "__main__":
    main()


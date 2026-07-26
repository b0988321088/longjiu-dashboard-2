import sqlite3
import os
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "dragon_assets.db")

def add_news_column_if_not_exists():
    if not os.path.exists(DB_PATH):
        print(f"Database file not found: {DB_PATH}")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 檢查 news 欄位是否存在
        cursor.execute("PRAGMA table_info(market_intel)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "news" not in column_names:
            print("Adding 'news' column to market_intel table...")
            cursor.execute("ALTER TABLE market_intel ADD COLUMN news TEXT")
            conn.commit()
            print("'news' column added successfully.")
        else:
            print("'news' column already exists in market_intel table.")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_news_column_if_not_exists()

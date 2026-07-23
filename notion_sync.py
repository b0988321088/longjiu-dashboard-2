import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/AppData/Local/hermes/.env"))
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

if __name__ == "__main__":
    print("Notion sync utilities loaded.")
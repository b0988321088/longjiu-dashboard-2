
import sys
sys.path.append("C:/Users/bot/Desktop/龍九系統/")
from hunter_intel import get_mock_news
import json
print(json.dumps(get_mock_news(), ensure_ascii=False, indent=2))

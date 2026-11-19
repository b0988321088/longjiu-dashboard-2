
import sys, os
sys.path.insert(0,"C:/Users/bot/Desktop/longjiu_system")
import mb_extract
src=r"C:\Users\bot\AppData\Local\hermes\cache\documents\doc_7d4cf91396b4_Moneybook_明細_20261119.zip"
out=r"C:\Users\bot\Desktop\longjiu_system\moneybook"
os.makedirs(out, exist_ok=True)
files=mb_extract.extract(src,out)
print(files)

# _ocr_wrap.ps1 — OCR wrapper (utf-8-sig)
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\AppData\Local\hermes\cache\images\img_f1e469fae0e8.jpg"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out.txt" -Encoding utf8

$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\AppData\Local\hermes\cache\images\img_2e3a70ab5f73.jpg"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out7.txt" -Encoding utf8

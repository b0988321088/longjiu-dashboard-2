$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\AppData\Local\hermes\cache\images\img_d943a065f3c4.jpg"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out2.txt" -Encoding utf8

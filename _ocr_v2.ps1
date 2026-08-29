
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_v2_full.png"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_v2_full.txt" -Encoding utf8

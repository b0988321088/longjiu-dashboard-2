
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_fullpage.png"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_fullpage.txt" -Encoding utf8

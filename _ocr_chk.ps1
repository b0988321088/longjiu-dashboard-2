$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$r = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_chk_cover.jpg"
$r | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_chk.txt" -Encoding utf8

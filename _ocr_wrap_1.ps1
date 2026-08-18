$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$r = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_ocr_tmp_1.jpg"
$r | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out_1.txt" -Encoding utf8

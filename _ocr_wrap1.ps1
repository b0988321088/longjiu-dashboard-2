$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_ocr_in1.jpg"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out1.txt" -Encoding utf8


$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_ocr_conv5.png"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_out5.txt" -Encoding utf8

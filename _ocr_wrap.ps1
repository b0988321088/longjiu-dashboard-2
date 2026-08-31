$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$result = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\Users\bot\Desktop\longjiu_system\_conv_img_e9be599cb30c.png"
$result | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_img_e9be599cb30c.jpg.txt" -Encoding utf8

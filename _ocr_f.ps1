$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$r = & "C:\Users\bot\Desktop\longjiu_system\ocr_win.ps1" -ImagePath "C:\\Users\\bot\\Desktop\\longjiu_system\\_frames\\v2_t2.jpg"
$r | Out-File -FilePath "C:\Users\bot\Desktop\longjiu_system\_ocr_f.txt" -Encoding utf8

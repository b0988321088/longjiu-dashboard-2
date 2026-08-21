$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$base = "C:\Users\bot\Desktop\longjiu_system"
$result = & "$base\ocr_win.ps1" -ImagePath "$base\_ocr_prep_7.jpg"
$result | Out-File -FilePath "$base\_ocr_out_7.txt" -Encoding utf8
Write-Output "DONE"

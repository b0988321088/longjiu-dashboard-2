$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$base = "C:\Users\bot\Desktop\longjiu_system"
foreach ($i in 1..3) {
    $result = & "$base\ocr_win.ps1" -ImagePath "$base\_ocr_prep_6_$i.jpg"
    $result | Out-File -FilePath "$base\_ocr_out_6_$i.txt" -Encoding utf8
}
Write-Output "DONE"

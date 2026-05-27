$ErrorActionPreference = "Stop"

$soundDir = Join-Path $PSScriptRoot "random_events_assets\sounds"
$sounds = Get-ChildItem -LiteralPath $soundDir -Filter "*.wav" | Sort-Object Name

foreach ($sound in $sounds) {
  Write-Host "Playing $($sound.Name)"
  $player = New-Object System.Media.SoundPlayer $sound.FullName
  $player.PlaySync()
}

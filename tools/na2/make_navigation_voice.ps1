# Generates Navigation Assist's spoken prompts with Windows' built-in voice (offline), 48 kHz mono 16-bit, into
# frogpilot/assets/navigation_voice/<id>.wav. Then run tools/na2/finish_navigation_voice.py to even out the loudness.
#   powershell -File tools/na2/make_navigation_voice.ps1
Add-Type -AssemblyName System.Speech
$out = Join-Path $PSScriptRoot "..\..\frogpilot\assets\navigation_voice"
New-Item -ItemType Directory -Force $out | Out-Null
$phrases = [ordered]@{
  "exit_right_ahead"        = "Exit on the right, coming up."
  "exit_left_ahead"         = "Exit on the left, coming up."
  "turn_right_ahead"        = "Right turn, coming up."
  "turn_left_ahead"         = "Left turn, coming up."
  "keep_right_ahead"        = "Keep right at the fork, coming up."
  "keep_left_ahead"         = "Keep left at the fork, coming up."
  "ramp_right_ahead"        = "Ramp on the right, coming up."
  "ramp_left_ahead"         = "Ramp on the left, coming up."
  "move_right_exit"         = "Move right for your exit."
  "move_left_exit"          = "Move left for your exit."
  "move_right_turn"         = "Move right for your turn."
  "move_left_turn"          = "Move left for your turn."
  "exit_lane_opening_right" = "Exit lane opening on the right."
  "exit_lane_opening_left"  = "Exit lane opening on the left."
  "stay_in_lane"            = "Stay in this lane."
  "any_lane"                = "Any lane is fine."
}
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice("Microsoft Zira Desktop")
$synth.Rate = 0
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($id in $phrases.Keys) {
  $file = Join-Path $out "$id.wav"
  $synth.SetOutputToWaveFile($file, $format)
  $synth.Speak($phrases[$id])
  $synth.SetOutputToNull()
  Write-Output "$id : $($phrases[$id])"
}
$synth.Dispose()

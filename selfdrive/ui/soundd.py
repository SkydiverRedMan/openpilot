import math
import numpy as np
import time
import wave

from pathlib import Path

from typing import Any

from cereal import car, custom, messaging
from openpilot.common.basedir import BASEDIR
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.realtime import Ratekeeper
from openpilot.common.retry import retry
from openpilot.common.swaglog import cloudlog

from openpilot.system import micd

from openpilot.frogpilot.common import frogpilot_paths, frogpilot_variables

SAMPLE_RATE = 48000
SAMPLE_BUFFER = 4096 # (approx 100ms)
MAX_VOLUME = 1.0
MIN_VOLUME = 0.1
CONTROLS_TIMEOUT = 5 # 5 seconds
FILTER_DT = 1. / (micd.SAMPLE_RATE / micd.FFT_SAMPLES)

AMBIENT_DB = 30 # DB where MIN_VOLUME is applied
DB_SCALE = 30 # AMBIENT_DB + DB_SCALE is where MAX_VOLUME is applied

AudibleAlert = car.CarControl.HUDControl.AudibleAlert

# FrogPilot variables
FrogPilotAudibleAlert = custom.FrogPilotCarControl.HUDControl.AudibleAlert

# Keith: Navigation Assist's spoken prompts (navigationAssist.voicePrompt / voicePromptCount). A prompt plays only while
# no openpilot or FrogPilot alert is sounding, and any alert cuts it off at once.
NAV_VOICE_DIR = BASEDIR + "/frogpilot/assets/navigation_voice"
KEITH_STARTUP_SOUND = Path(BASEDIR) / "frogpilot/assets/other_sounds/woo_hoo.wav"


def load_nav_voices() -> dict[str, np.ndarray]:
  import os
  voices: dict[str, np.ndarray] = {}
  if not os.path.isdir(NAV_VOICE_DIR):
    return voices
  for name in os.listdir(NAV_VOICE_DIR):
    if not name.endswith(".wav"):
      continue
    try:
      with wave.open(os.path.join(NAV_VOICE_DIR, name), 'r') as wavefile:
        if (wavefile.getnchannels(), wavefile.getsampwidth(), wavefile.getframerate()) != (1, 2, SAMPLE_RATE):
          continue
        data = wavefile.readframes(wavefile.getnframes())
      voices[name[:-4]] = np.frombuffer(data, dtype=np.int16).astype(np.float32) / (2**16/2)
    except Exception:
      cloudlog.exception(f"soundd: could not load navigation voice {name}")
  return voices


sound_list: dict[Any, tuple[str, int | None, float]] = {
  # AudibleAlert, file name, play count (none for infinite)
  AudibleAlert.engage: ("engage.wav", 1, MAX_VOLUME),
  AudibleAlert.disengage: ("disengage.wav", 1, MAX_VOLUME),
  AudibleAlert.refuse: ("refuse.wav", 1, MAX_VOLUME),

  AudibleAlert.prompt: ("prompt.wav", 1, MAX_VOLUME),
  AudibleAlert.promptRepeat: ("prompt.wav", None, MAX_VOLUME),
  AudibleAlert.promptDistracted: ("prompt_distracted.wav", None, MAX_VOLUME),

  AudibleAlert.warningSoft: ("warning_soft.wav", None, MAX_VOLUME),
  AudibleAlert.warningImmediate: ("warning_immediate.wav", None, MAX_VOLUME),

  # FrogPilot sounds
  FrogPilotAudibleAlert.angry: ("angry.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.continued: ("continued.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.dejaVu: ("dejaVu.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.doc: ("doc.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.fart: ("fart.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.firefox: ("firefox.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.goat: ("goat.wav", None, MAX_VOLUME),
  FrogPilotAudibleAlert.hal9000: ("hal9000.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.mail: ("mail.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.nessie: ("nessie.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.noice: ("noice.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.startup: ("startup.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.thisIsFine: ("this_is_fine.wav", 1, MAX_VOLUME),
  FrogPilotAudibleAlert.uwu: ("uwu.wav", 1, MAX_VOLUME),
}

def check_controls_timeout_alert(sm):
  controls_missing = time.monotonic() - sm.recv_time['controlsState']

  if controls_missing > CONTROLS_TIMEOUT:
    if sm['controlsState'].enabled and (controls_missing - CONTROLS_TIMEOUT) < 10:
      return True

  return False


class Soundd:
  def __init__(self):
    self.current_alert = AudibleAlert.none
    self.current_volume = MIN_VOLUME
    self.current_sound_frame = 0

    self.controls_timeout_alert = False

    self.spl_filter_weighted = FirstOrderFilter(0, 2.5, FILTER_DT, initialized=False)

    # FrogPilot variables
    self.openpilot_crashed_played = False

    self.theme_update_count = 0

    self.the_pond_request_sock = messaging.sub_sock("thePondRequest")
    self.ui_request_sock = messaging.sub_sock("frogpilotUIRequest")

    self.error_log = frogpilot_paths.ERROR_FILE_PATH
    self.random_events_directory = frogpilot_paths.RANDOM_EVENTS_PATH / "sounds"

    self.frogpilot_toggles = frogpilot_variables.get_frogpilot_toggles()

    self.sound_source = None
    self.startup_sound_file = ""

    self.nav_voices = load_nav_voices()
    self.nav_voice: np.ndarray | None = None   # the prompt being spoken
    self.nav_voice_frame = 0
    self.nav_voice_count: int | None = None    # last voicePromptCount seen (None until the first message)

    self.update_frogpilot_sounds()

  def load_sounds(self):
    loaded_sounds: dict[int, np.ndarray] = {}

    # Load all sounds
    for sound in sound_list:
      filename, play_count, volume = sound_list[sound]

      # FrogPilot variables
      random_events_path = self.random_events_directory / filename
      sounds_path = self.sound_directory / filename

      if sound == FrogPilotAudibleAlert.startup and KEITH_STARTUP_SOUND.exists():
        # Keith: his Woo Hoo greets every start-up (after the paramotor boot picture); every other sound is the theme's
        path = str(KEITH_STARTUP_SOUND)
      elif random_events_path.exists():
        goat_scream = sound == FrogPilotAudibleAlert.goat and self.frogpilot_toggles.goat_scream_alert
        if not self.frogpilot_toggles.random_events and not goat_scream:
          continue

        path = str(random_events_path)
      elif sounds_path.exists():
        path = str(sounds_path)
      else:
        if filename == "startup.wav":
          filename = "engage.wav"
        path = BASEDIR + "/selfdrive/assets/sounds/" + filename
      wavefile = wave.open(path, 'r')

      assert wavefile.getnchannels() == 1
      assert wavefile.getsampwidth() == 2
      assert wavefile.getframerate() == SAMPLE_RATE

      if sound == FrogPilotAudibleAlert.startup:
        self.startup_sound_file = path

      length = wavefile.getnframes()
      loaded_sounds[sound] = np.frombuffer(wavefile.readframes(length), dtype=np.int16).astype(np.float32) / (2**16/2)

    # FrogPilot variables
    if self.current_alert not in loaded_sounds:
      self.current_alert = AudibleAlert.none

    self.loaded_sounds = loaded_sounds

  def get_sound_data(self, frames): # get "frames" worth of data from the current alert sound, looping when required

    ret = np.zeros(frames, dtype=np.float32)

    # Keith: a navigation prompt plays only when no alert is sounding; an alert cuts it off at once
    if self.current_alert != AudibleAlert.none:
      self.nav_voice = None
    elif self.nav_voice is not None:
      chunk = self.nav_voice[self.nav_voice_frame:self.nav_voice_frame + frames]
      ret[:len(chunk)] = chunk
      self.nav_voice_frame += len(chunk)
      if self.nav_voice_frame >= len(self.nav_voice):
        self.nav_voice = None
      return ret * self.current_volume

    if self.current_alert != AudibleAlert.none:
      num_loops = sound_list[self.current_alert][1]
      sound_data = self.loaded_sounds[self.current_alert]
      written_frames = 0

      current_sound_frame = self.current_sound_frame % len(sound_data)
      loops = self.current_sound_frame // len(sound_data)

      while written_frames < frames and (num_loops is None or loops < num_loops):
        available_frames = sound_data.shape[0] - current_sound_frame
        frames_to_write = min(available_frames, frames - written_frames)
        ret[written_frames:written_frames+frames_to_write] = sound_data[current_sound_frame:current_sound_frame+frames_to_write]
        written_frames += frames_to_write
        self.current_sound_frame += frames_to_write

    # FrogPilot variables
    volume = self.alert_volumes.get(self.current_alert, self.current_volume)
    if self.current_alert in (AudibleAlert.promptDistracted, AudibleAlert.warningSoft, AudibleAlert.warningImmediate):
      volume = max(volume, self.current_volume)

    return ret * volume

  def callback(self, data_out: np.ndarray, frames: int, time, status) -> None:
    if status:
      cloudlog.warning(f"soundd stream over/underflow: {status}")
    data_out[:frames, 0] = self.get_sound_data(frames)

  def update_nav_voice(self, sm):
    if not sm.updated['navigationAssist']:
      return
    na = sm['navigationAssist']
    count = int(na.voicePromptCount)
    if self.nav_voice_count is None:            # don't replay an old prompt when soundd (re)starts mid-drive
      self.nav_voice_count = count
      return
    if count == self.nav_voice_count:
      return
    self.nav_voice_count = count
    voice = self.nav_voices.get(str(na.voicePrompt))
    if voice is not None and self.current_alert == AudibleAlert.none and self.nav_voice is None:
      self.nav_voice_frame = 0
      self.nav_voice = voice

  def update_alert(self, new_alert):
    current_alert_played_once = self.current_alert == AudibleAlert.none or self.current_sound_frame > len(self.loaded_sounds[self.current_alert])
    if self.current_alert != new_alert and (new_alert != AudibleAlert.none or current_alert_played_once):
      self.current_alert = new_alert
      self.current_sound_frame = 0
      if new_alert == FrogPilotAudibleAlert.startup:   # Keith: proof in the log that the start-up sound played
        cloudlog.info(f"keith startup sound playing: {self.startup_sound_file}")

  def get_audible_alert(self, sm):
    # FrogPilot variables
    test_requests = [msg.frogpilotUIRequest for msg in messaging.drain_sock(self.ui_request_sock) if msg.frogpilotUIRequest.which() == 'testAlert']
    test_requests += [msg.thePondRequest.request for msg in messaging.drain_sock(self.the_pond_request_sock)
                      if msg.thePondRequest.request.which() == 'testAlert']
    if test_requests:
      test_alert = getattr(AudibleAlert, test_requests[-1].testAlert)
      test_volume = test_requests[-1].testAlertVolume

      if test_volume <= 100:
        self.alert_volumes[test_alert] = test_volume / 100.0
      else:
        self.alert_volumes.pop(test_alert, None)

      self.update_alert(test_alert)
    elif not self.openpilot_crashed_played and self.error_log.is_file():
      if self.frogpilot_toggles.random_events:
        self.update_alert(FrogPilotAudibleAlert.fart)
      else:
        self.update_alert(AudibleAlert.prompt)

      self.openpilot_crashed_played = True
    elif sm.updated['controlsState']:
      new_alert = sm['controlsState'].alertSound.raw

      # FrogPilot variables
      new_frogpilot_alert = sm['frogpilotControlsState'].alertSound.raw

      if new_alert == AudibleAlert.none and new_frogpilot_alert in self.loaded_sounds:
        new_alert = new_frogpilot_alert

      self.update_alert(new_alert)
    elif check_controls_timeout_alert(sm):
      self.update_alert(AudibleAlert.warningImmediate)
      self.controls_timeout_alert = True
    elif self.controls_timeout_alert:
      self.update_alert(AudibleAlert.none)
      self.controls_timeout_alert = False

  def calculate_volume(self, weighted_db):
    volume = ((weighted_db - AMBIENT_DB) / DB_SCALE) * (MAX_VOLUME - MIN_VOLUME) + MIN_VOLUME
    return math.pow(10, (np.clip(volume, MIN_VOLUME, MAX_VOLUME) - 1))

  @retry(attempts=7, delay=3)
  def get_stream(self, sd):
    # reload sounddevice to reinitialize portaudio
    sd._terminate()
    sd._initialize()
    return sd.OutputStream(channels=1, samplerate=SAMPLE_RATE, callback=self.callback, blocksize=SAMPLE_BUFFER)

  def soundd_thread(self):
    # sounddevice must be imported after forking processes
    import sounddevice as sd

    sm = messaging.SubMaster(['controlsState', 'microphone', 'frogpilotControlsState', 'frogpilotPlan', 'navigationAssist'])

    with self.get_stream(sd) as stream:
      rk = Ratekeeper(20)

      cloudlog.info(f"soundd stream started: {stream.samplerate=} {stream.channels=} {stream.dtype=} {stream.device=}, {stream.blocksize=}")
      while True:
        sm.update(0)

        if sm.updated['microphone'] and self.current_alert == AudibleAlert.none and self.nav_voice is None: # only update volume filter when not playing alert
          self.spl_filter_weighted.update(sm["microphone"].soundPressureWeightedDb)
          self.current_volume = self.calculate_volume(float(self.spl_filter_weighted.x))

        # Update FrogPilot variables
        theme_updated = sm['frogpilotPlan'].themeUpdateCount != self.theme_update_count
        frogpilot_toggles = frogpilot_variables.get_frogpilot_toggles(sm)
        if theme_updated or frogpilot_toggles is not self.frogpilot_toggles:
          self.frogpilot_toggles = frogpilot_toggles
          self.theme_update_count = sm['frogpilotPlan'].themeUpdateCount

          stream = self.update_frogpilot_sounds(sd, stream)

        self.get_audible_alert(sm)
        self.update_nav_voice(sm)

        rk.keep_time()

        assert stream.active

  # FrogPilot variables
  def update_frogpilot_sounds(self, sd=None, stream=None):
    volumes = {
      AudibleAlert.engage: self.frogpilot_toggles.engage_volume,
      AudibleAlert.disengage: self.frogpilot_toggles.disengage_volume,
      AudibleAlert.refuse: self.frogpilot_toggles.refuse_volume,

      AudibleAlert.prompt: self.frogpilot_toggles.prompt_volume,
      AudibleAlert.promptRepeat: self.frogpilot_toggles.prompt_volume,
      AudibleAlert.promptDistracted: self.frogpilot_toggles.prompt_distracted_volume,

      AudibleAlert.warningSoft: self.frogpilot_toggles.warning_soft_volume,
      AudibleAlert.warningImmediate: self.frogpilot_toggles.warning_immediate_volume,

      FrogPilotAudibleAlert.goat: self.frogpilot_toggles.prompt_volume,
      FrogPilotAudibleAlert.startup: self.frogpilot_toggles.engage_volume
    }
    self.alert_volumes = {alert: volume / 100.0 for alert, volume in volumes.items() if volume <= 100}

    self.sound_directory = frogpilot_paths.ACTIVE_THEME_PATH / "sounds"

    try:
      sound_inode = self.sound_directory.stat().st_ino
    except FileNotFoundError:
      sound_inode = None
    sound_source = (self.sound_directory.resolve(), sound_inode, self.frogpilot_toggles.random_events, self.frogpilot_toggles.goat_scream_alert)
    if sound_source != self.sound_source:
      self.load_sounds()

      self.sound_source = sound_source

      if stream is not None:
        stream.close()
        stream = self.get_stream(sd)
        stream.start()

    return stream

def main():
  s = Soundd()
  s.soundd_thread()


if __name__ == "__main__":
  main()

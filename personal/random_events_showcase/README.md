# FrogPilot Random Events Showcase

This folder collects the funny FrogPilot sounds, popups, and visual assets that can show up during drives.

## Folders

- `random_events_assets/sounds/` - the FrogPilot random-event WAV files.
- `random_events_assets/icons/` - surprise UI images, including the random home button and `ferg.png`.
- `random_events_assets/steering_wheels/` - temporary steering wheel animations used by some random events.
- `stock_openpilot_sounds/` - normal openpilot alert sounds used by some FrogPilot banners.
- `holiday_theme_sounds/` - seasonal theme engage/disengage/startup sounds.

## Quick Listen

Open any `.wav` directly, or run this from PowerShell:

```powershell
.\personal\random_events_showcase\play_random_event_sounds.ps1
```

## Random Event Popups

| Event | Banner top | Banner bottom | Sound | Extra visual | Trigger |
| --- | --- | --- | --- | --- | --- |
| `accel30` | `UwU u went a bit fast there!` | `(⁄ ⁄•⁄ω⁄•⁄ ⁄)` | `uwu.wav` | `weeb_wheel.gif` | Acceleration peaks between 3.0 and 3.5 m/s^2, then settles. |
| `accel35` | `I ain't giving you no tree-fiddy` | `You damn Loch Ness Monsta!` | `nessie.wav` | `tree_fiddy.gif` | Acceleration peaks between 3.5 and 4.0 m/s^2, then settles. |
| `accel40` | `Great Scott!` | `🚗💨` | `doc.wav` | `great_scott.gif` | Acceleration peaks at 4.0 m/s^2 or higher, then settles. |
| `dejaVuCurve` | `♬♪ Deja vu! ᕕ(⌐■_■)ᕗ ♪♬` | `🏎️` | `dejaVu.wav` | none | High lateral acceleration in a curve while cruising. |
| `firefoxSteerSaturated` | `IE Has Stopped Responding...` | `Turn Exceeds Steering Limit` | `firefox.wav` | `firefox.gif` | Rare random replacement during steering saturation. |
| `goatSteerSaturated` | `JESUS TAKE THE WHEEL!!` | `Turn Exceeds Steering Limit` | `goat.wav` | `goat.gif` | Steering saturation alert, also used as a random steering-saturation variant. |
| `thisIsFineSteerSaturated` | `This is fine ☕` | `Turn Exceeds Steering Limit` | `this_is_fine.wav` | `this_is_fine.gif` | Rare random replacement during steering saturation. |
| `hal9000` | `I'm sorry Dave` | `I'm afraid I can't do that...` | `hal9000.wav` | none | A no-entry alert occurs while random events are enabled. |
| `openpilotCrashedRandomEvent` | `openpilot crashed 💩` | `Please post the 'Error Log' in the FrogPilot Discord!` | `fart.wav` | maybe `ferg.png` | Error log exists and random events are enabled. On some starts it shows `ferg.png` instead of the text banner. |
| `toBeContinued` | `To be continued...` | `⬅️` | `continued.wav` | none | Forward-collision warning or stock AEB alert. |
| `vCruise69` | `Lol 69` | blank | `noice.wav` | none | Cruise speed is around 69 mph. |
| `yourFrogTriedToKillMe` | `Your Frog tried to kill me...` | `👺` | `angry.wav` | none | Forward-collision warning or stock AEB alert. |
| `youveGotMail` | `You've got mail! 📧` | blank | `mail.wav` | none | Rare random event when Always On Lateral becomes enabled. |

## Random Sound Inventory

| Sound file | Duration | Used by |
| --- | ---: | --- |
| `angry.wav` | 3.115s | `yourFrogTriedToKillMe` |
| `continued.wav` | 6.631s | `toBeContinued` |
| `dejaVu.wav` | 4.000s | `dejaVuCurve` |
| `doc.wav` | 2.594s | `accel40` |
| `fart.wav` | 4.004s | `openpilotCrashedRandomEvent` |
| `firefox.wav` | 4.321s | `firefoxSteerSaturated` |
| `goat.wav` | 1.739s | `goatSteerSaturated` |
| `hal9000.wav` | 3.599s | `hal9000` |
| `mail.wav` | 2.670s | `youveGotMail` |
| `nessie.wav` | 2.322s | `accel35` |
| `noice.wav` | 1.879s | `vCruise69` |
| `startup.wav` | 3.008s | startup/holiday alert override; in this custom branch it is Keith's WooHoo sound |
| `this_is_fine.wav` | 2.000s | `thisIsFineSteerSaturated` |
| `uwu.wav` | 0.468s | `accel30` |

## Related FrogPilot Banners

These are not all random events, but they can look like little surprise popups:

| Event | Banner top | Banner bottom | Sound |
| --- | --- | --- | --- |
| `customStartupAlert` | user-configured startup top text | user-configured startup bottom text | `startup.wav` / normal startup sound |
| `greenLight` | `Light turned green` | blank | `prompt.wav` |
| `laneChangeBlockedLoud` | `Car Detected in Blindspot` | blank | `warning_soft.wav` |
| `leadDeparting` | `Lead departed` | blank | `prompt.wav` |
| `speedLimitChanged` | `Speed limit changed` | blank | `prompt.wav` |
| `trafficModeActive` | `Traffic Mode enabled` | blank | `prompt.wav` |
| `trafficModeInactive` | `Traffic Mode Disabled` | blank | `prompt.wav` |
| `turningLeft` | `Turning left` | blank | none |
| `turningRight` | `Turning right` | blank | none |
| `holidayActive` | holiday-specific message, like `Happy Halloween! 🎃` | blank | `startup.wav` |
| `noLaneAvailable` | `No lane available` | detected lane width message | none |
| `torqueNNLoad` | `NNFF Torque Controller loaded` | model name | `engage.wav` |

## Holiday Messages

Holiday popups are generated from the active holiday theme:

- `new_years` - `Happy New Year! 🎉`
- `valentines` - `Happy Valentine's Day! ❤️`
- `st_patricks` - `Happy St. Patrick's Day! 🍀`
- `world_frog_day` - `Happy World Frog Day! 🐸`
- `april_fools` - `Happy April Fool's Day! 🤡`
- `easter_week` - `Happy Easter! 🐰`
- `may_the_fourth` - `May the 4th be with you! 🚀`
- `cinco_de_mayo` - `¡Feliz Cinco de Mayo! 🌮`
- `stitch_day` - `Happy Stitch Day! 💙`
- `fourth_of_july` - `Happy Fourth of July! 🎆`
- `halloween_week` - `Happy Halloween! 🎃`
- `thanksgiving_week` - `Happy Thanksgiving! 🦃`
- `christmas_week` - `Merry Christmas! 🎄`

## Source Files

- Event popup text: `selfdrive/controls/lib/events.py`
- Random-event trigger logic: `frogpilot/controls/lib/frogpilot_events.py`
- Sound mapping and loading behavior: `selfdrive/ui/soundd.py`
- Random-event assets: `frogpilot/assets/random_events/`

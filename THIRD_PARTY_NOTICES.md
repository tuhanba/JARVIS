# Third-party notices

## Code in this repository

| Component | License | Notes |
|---|---|---|
| Original J.A.R.V.I.S by GauravSingh9356 | MIT (© 2020) | Base project; see `LICENSE`. |

No source code has been copied from other projects. Python packages are installed from PyPI under their own
licenses (see `requirements.txt`); they are not vendored here.

## Reference projects (ideas only, no code copied)

The development plan (`docs/JARVIS_MASTER_PLAN.md`, section 3) studied these projects. Features inspired by
them are implemented independently. Before copying any code from them, check license compatibility and add an
entry to the table above.

| Project | Reviewed commit | License seen |
|---|---|---|
| Dodaios / PersonalJarvis | `ae629b4b` | Apache-2.0 |
| Axx33284/jarvis | `6b56a4e3` | no LICENSE file found (all rights reserved by default) — do not copy |
| AgenticSeek (Fosowl) | `b46bcca4` | GPL-3.0 — copying would require GPL for derived code |
| isair/jarvis | `89071311` | custom non-commercial license — do not copy |

## Models and online services

- Ollama models are downloaded by the user (`ollama pull ...`); each model has its own license (see
  `ollama show <model> --license`). Record the license of any model recommended by the setup wizard here.
- Online services used by the current voice path: Google speech recognition (via `SpeechRecognition`),
  Microsoft Edge TTS (via `edge-tts`). Their terms apply when these are used.

"""Local-first voice pipeline (Stage C).

- arayuzler.py   provider contracts (STT, TTS, wake word, turn detection)
- metin_hazirla  Turkish text normalisation for TTS
- vad.py         energy VAD + end-of-turn detection with pre-roll, bounded buffers
- stt.py         faster-whisper (local, multilingual, Turkish) | Google (online, opt-in)
- tts.py         Piper Turkish voice (local) | SAPI/pyttsx3 Turkish voice (local) | Edge (online, opt-in)
- secim.py       which provider runs, and an honest status for the UI
- kur.py         downloads the local models, showing sizes and destinations

Online providers are used only when JARVIS_SES_CEVRIMICI=1. If no local
Turkish voice exists JARVIS says so instead of reading Turkish with an
English voice."""

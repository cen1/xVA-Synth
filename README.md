# xVA-Synth

This is a fork of [xVA-Synth](https://github.com/DanRuta/xVA-Synth) which is currently no longer maintained but is still the best TTS for game characters out there that I know of.

The focus of this fork is to have a TTS to interact with various AIs. The driving force of getting this to work is to have an EDI personal assistant. *Shepard?*

Python dependencies are updated to latest and focused on making the server TTS work as a Linux service. The state of the UI is unknown, same for Windows and CUDA.

Tested on Debian Trixie with ROCm.

# TLDR

```bash
sudo apt-get install -y espeak-ng ffmpeg python3 python3-pip python3-venv
python -m venv ~/.venvs/xvasynth
source ~/.venvs/xvasynth/bin/activate
pip install -r requirements.txt
# For AMD GPU (ROCm): pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/rocm6.3
git clone https://github.com/DanRuta/xva-trainer && cp -r xva-trainer/lib/_dev/* ~/.venvs/xvasynth/lib/python3.11/site-packages/
python server.py
# In another terminal
./tts.py "I'm EDI, The Enhanced Defense Intelligence installed aboard the Normandy." --gpu --voice edi
```

## Docker

```bash
docker compose up --build -d
# Place models in ./resources/app/models/ (see Model Setup below)
./tts.py "Hello from Docker"
```

## Model Setup

Place your model files in the appropriate directory structure:

```
resources/app/models/
└── [game_name]/
    ├── [model_name].pt       # PyTorch model file
    └── [model_name].json     # Model configuration
```

Example for Mass Effect EDI:
```
resources/app/models/masseffect/
├── me_edi.pt
└── me_edi.json
```

The JSON file should contain model metadata including `base_speaker_emb` for voice identity.

You can download the models from [Nexusmod](https://www.nexusmods.com/skyrimspecialedition/mods/44184) (See Supported games section for different games).

Extract to `resources/app/models/<gamename>/...`. The final folder should include .json, .pt and .wav.

## Running the Server

Start the xVA-Synth server:

```bash
python server.py
```

The server will start on `http://localhost:8008` by default.

## Command Line TTS

`tts.py` is the primary CLI for text-to-speech:

```bash
./tts.py "Your text here"                  # CPU, EDI voice (defaults)
./tts.py "Your text here" --gpu            # GPU acceleration
./tts.py "Your text here" --voice edi      # Specify voice
./tts.py --list-voices                     # List available voices
./tts.py --no-play "text"                  # Synthesize without playing, prints file path

# Pipe arbitrary text
echo "Your text here" | ./tts.py

# Stream sentence-by-sentence (lower latency — starts playing before input ends)
some_command | ./tts.py --stream
```

## Claude CLI Integration

Automatically speak Claude's prose responses aloud using Claude Code's `Stop` hook.

`tts_hook.py` reads the session transcript after each response, strips code blocks and technical content, and pipes the remaining prose to `tts.py`.

### Setup

Add the hook to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/xVA-Synth/tts_hook.py --voice edi",
            "async": true
          }
        ]
      }
    ]
  }
}
```

The hook runs asynchronously — audio plays in the background while you continue the conversation.

### Changing the voice

Pass `--voice NAME` in the hook command to change which voice speaks Claude's responses:

```json
"command": "python3 /path/to/xVA-Synth/tts_hook.py --voice edi"
```

To see available voices:

```bash
./tts.py --list-voices
```

Voice names match the suffix of the model JSON filename — e.g. `me_edi.json` → `--voice edi`.

GPU acceleration for the hook can also be enabled with `--gpu`:

```json
"command": "python3 /path/to/xVA-Synth/tts_hook.py --voice edi --gpu"
```

### What gets filtered out

The hook speaks prose but skips:
- Fenced code blocks and inline code
- File paths and shell prompts
- URLs
- Lines that are mostly non-alphabetic (JSON, diffs, etc.)

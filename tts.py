#!/usr/bin/env python3

# xVA-Synth Text-to-Speech CLI
# Usage: ./tts.py "text" [--gpu] [--voice NAME] [--stream]

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

SERVER_URL = "http://localhost:8008"


def find_player():
    for player in ("paplay", "aplay", "ffplay", "mpv"):
        if shutil.which(player):
            return player
    return None


def play_file(path, player):
    if player == "ffplay":
        subprocess.run(["ffplay", "-nodisp", "-autoexit", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif player == "mpv":
        subprocess.run(["mpv", "--no-video", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run([player, path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def post(endpoint, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SERVER_URL}/{endpoint}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def find_model(voice):
    matches = glob.glob(f"resources/app/models/**/*_{voice}.json", recursive=True)
    if not matches:
        return None, None
    model_json = matches[0]
    model_path = model_json[: -len(".json")]
    return model_json, model_path


def list_voices():
    for path in sorted(glob.glob("resources/app/models/**/*.json", recursive=True)):
        name = os.path.basename(path)[: -len(".json")]
        name = name.split("_", 1)[-1] if "_" in name else name
        print(f"  {name}")


def load_base_emb(model_json):
    with open(model_json) as f:
        emb = json.load(f)["games"][0]["base_speaker_emb"]
    return ",".join(str(v) for v in emb)


def synthesize(text, model_path, base_emb, device, output_file):
    """Send one synthesis request and wait for the output file to appear."""
    container_path = "/app/resources/" + os.path.basename(output_file)
    post("synthesize", {
        "sequence": text,
        "pace": 1.0,
        "outfile": container_path,
        "vocoder": "n/a",
        "base_lang": "en",
        "base_emb": base_emb,
        "useSR": False,
        "useCleanup": False,
        "modelType": "xVAPitch",
        "device": device,
        "pluginsContext": "{}",
    })

    deadline = time.time() + 30
    while not os.path.exists(output_file):
        if time.time() > deadline:
            return False
        time.sleep(0.1)
    return True


def split_sentences(text):
    """Split text on sentence-ending punctuation, keeping the punctuation."""
    import re
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p.strip()]


def speak_text(text, model_path, base_emb, device, play, player, index=0):
    filename = f"tts_{os.getpid()}_{index}.wav"
    output_file = f"./resources/{filename}"
    ok = synthesize(text, model_path, base_emb, device, output_file)
    if not ok:
        print(f"Error: Audio file was not created for: {text!r}", file=sys.stderr)
        return
    if not play:
        print(output_file)
    else:
        play_file(output_file, player)
        os.remove(output_file)


def main():
    parser = argparse.ArgumentParser(description="xVA-Synth TTS CLI")
    parser.add_argument("text", nargs="?", help="Text to synthesize")
    parser.add_argument("--gpu", dest="device", action="store_const", const="gpu", default="cpu")
    parser.add_argument("--cpu", dest="device", action="store_const", const="cpu")
    parser.add_argument("--voice", default="edi", metavar="NAME")
    parser.add_argument("--no-play", dest="play", action="store_false", default=True)
    parser.add_argument("--stream", action="store_true",
                        help="Read from stdin, synthesize sentence by sentence")
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return

    # Determine text source
    if args.stream or (args.text is None and not sys.stdin.isatty()):
        text_sentences = None  # read from stdin below
    elif args.text:
        text_sentences = [args.text]
    else:
        parser.print_help(sys.stderr)
        print("\nAvailable voices:", file=sys.stderr)
        list_voices()
        sys.exit(1)

    model_json, model_path = find_model(args.voice)
    if not model_json:
        print(f"Error: Voice '{args.voice}' not found", file=sys.stderr)
        print("Available voices:", file=sys.stderr)
        list_voices()
        sys.exit(1)

    base_emb = load_base_emb(model_json)
    player = find_player() if args.play else None
    if args.play and not player:
        print("Error: No audio player found (paplay/aplay/ffplay/mpv)", file=sys.stderr)
        sys.exit(1)

    post("setDevice", {"device": args.device})
    post("loadModel", {
        "outputs": None,
        "model": model_path,
        "modelType": "xVAPitch",
        "base_lang": "en",
        "pluginsContext": "{}",
    })

    if text_sentences is not None:
        # Single arg mode
        for i, sentence in enumerate(split_sentences(text_sentences[0])):
            speak_text(sentence, model_path, base_emb, args.device, args.play, player, i)
    else:
        # Streaming stdin mode: synthesize each sentence as it arrives
        buffer = ""
        index = 0
        import re
        for line in sys.stdin:
            buffer += line
            # Flush on sentence boundaries
            while re.search(r'[.!?]\s', buffer):
                match = re.search(r'(?<=[.!?])\s+', buffer)
                if not match:
                    break
                sentence = buffer[:match.start() + 1].strip()
                buffer = buffer[match.end():]
                if sentence:
                    speak_text(sentence, model_path, base_emb, args.device, args.play, player, index)
                    index += 1
        # Speak any remaining text
        if buffer.strip():
            speak_text(buffer.strip(), model_path, base_emb, args.device, args.play, player, index)


if __name__ == "__main__":
    main()

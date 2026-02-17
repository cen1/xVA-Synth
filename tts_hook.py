#!/usr/bin/env python3
"""
Claude Code Stop hook — reads the last assistant response from the session
transcript, strips non-prose content, and pipes it to tts.py.

Register in ~/.claude/settings.json:
  {
    "hooks": {
      "Stop": [{"hooks": [{"type": "command", "command": "python3 /path/to/tts_hook.py", "async": true}]}]
    }
  }
"""

import json
import os
import re
import subprocess
import sys
import time


# ---------------------------------------------------------------------------
# Text filtering — keep only speakable prose
# ---------------------------------------------------------------------------

def strip_non_prose(text: str) -> str:
    # Remove fenced code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`\n]+`', '', text)
    # Remove markdown headers (keep the text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove markdown links — keep display text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove bold / italic markers
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)
    # Remove list markers (bullet / numbered) but keep the text
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Drop lines that look purely technical
    clean_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            clean_lines.append('')
            continue
        # File/shell paths
        if re.match(r'^[/~]', s) or s.startswith('./') or s.startswith('../'):
            continue
        # Shell prompts or command lines
        if s.startswith('$') or s.startswith('>') or s.startswith('#!'):
            continue
        # Lines that are mostly non-alpha (e.g. JSON, diffs)
        alpha = sum(c.isalpha() for c in s)
        if len(s) > 5 and alpha / len(s) < 0.4:
            continue
        clean_lines.append(line)

    text = '\n'.join(clean_lines)
    # Collapse excess blank lines and trim
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


# ---------------------------------------------------------------------------
# Transcript reading
# ---------------------------------------------------------------------------

def get_last_assistant_text(transcript_path: str) -> str | None:
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except OSError:
        return None

    entries = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    # Find the ID of the most recent assistant message.
    # One logical message spans multiple entries (thinking/text/tool_use blocks),
    # so we must collect text only from that specific message ID.
    last_id = None
    for entry in reversed(entries):
        msg = entry.get('message', {})
        if msg.get('role') == 'assistant':
            last_id = msg.get('id')
            if last_id:
                break

    if not last_id:
        return None

    # Collect all text blocks from entries belonging to that message ID.
    parts = []
    for entry in entries:
        msg = entry.get('message', {})
        if msg.get('id') != last_id:
            continue
        content = msg.get('content', [])
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    parts.append(block['text'])

    return '\n'.join(parts) if parts else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--voice', default='edi')
    parser.add_argument('--gpu', dest='device', action='store_const', const='gpu', default='cpu')
    parser.add_argument('--cpu', dest='device', action='store_const', const='cpu')
    args = parser.parse_args()

    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    # Avoid re-triggering if a stop hook already caused Claude to continue
    if hook_input.get('stop_hook_active'):
        return

    transcript_path = hook_input.get('transcript_path')
    if not transcript_path:
        return

    # Retry briefly — on the first turn of a new session the transcript may not
    # be fully written yet when the hook fires.
    text = None
    for _ in range(10):
        text = get_last_assistant_text(transcript_path)
        if text:
            break
        time.sleep(0.3)
    if not text:
        return

    prose = strip_non_prose(text)
    if not prose:
        return

    pid_file = '/tmp/xvasynth_tts.pid'

    # Kill any in-progress TTS so new response always starts fresh.
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 9)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        os.remove(pid_file)

    tts_script = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'tts.py')
    proc = subprocess.Popen(
        [sys.executable, tts_script, '--stream', '--voice', args.voice, f'--{args.device}'],
        stdin=subprocess.PIPE,
        cwd=os.path.dirname(tts_script),
    )

    with open(pid_file, 'w') as f:
        f.write(str(proc.pid))

    proc.communicate(input=prose.encode())

    if os.path.exists(pid_file):
        os.remove(pid_file)


if __name__ == '__main__':
    main()

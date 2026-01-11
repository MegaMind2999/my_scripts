import os
import re
import json
import subprocess
import argparse
import time
import urllib.parse
from pathlib import Path

def clean_query_text(text):
    """
    Purifies strings from BOTH metadata and filenames.
    Removes: (mp3_160k), [Official Video], (Live), feat. Artist, etc.
    """
    if not text:
        return ""
    # Remove everything inside parentheses () or square brackets []
    text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
    # Remove common technical/marketing suffixes (case-insensitive)
    text = re.sub(r'(?i)official\s+(music\s+)?video|lyric\s+video|full\s+audio|high\s+quality|160k|320k', '', text)
    # Remove "feat." or "ft." and everything after it for a cleaner search
    text = re.sub(r'(?i)(feat\.|ft\.).*', '', text)
    return text.strip().strip('-').strip()

def get_lyrics_from_lrclib(artist, title):
    try:
        # Clean both artist and title right before the API call
        c_artist = clean_query_text(artist)
        c_title = clean_query_text(title)
        
        if not c_title:
            return None
            
        params = {"track_name": c_title}
        if c_artist:
            params["artist_name"] = c_artist
            
        url = f"https://lrclib.net/api/search?{urllib.parse.urlencode(params)}"
        
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "10", url],
            capture_output=True, text=True
        )
        
        if result.returncode == 0 and result.stdout:
            results = json.loads(result.stdout)
            if results:
                # Return synced lyrics if available, otherwise plain
                return results[0].get('syncedLyrics') or results[0].get('plainLyrics')
    except Exception as e:
        print(f"    [!] API Error: {e}")
    return None

def extract_metadata(file_path):
    """Extracts ID3 tags using ffprobe (Matches your original mydl.py logic)"""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_entries", "format_tags=artist,title", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            tags = json.loads(result.stdout).get('format', {}).get('tags', {})
            return tags.get('artist', tags.get('ARTIST', '')), tags.get('title', tags.get('TITLE', ''))
    except:
        pass
    return "", ""

def process_folder(folder_path):
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f"[!] Directory not found: {folder_path}")
        return

    files = list(folder.glob("*.mp3"))
    print(f"[*] Found {len(files)} MP3s. Checking for missing lyrics...")
    
    for i, file_path in enumerate(files, 1):
        lrc_path = file_path.with_suffix('.lrc')
        
        # --- THE SKIP LOGIC ---
        if lrc_path.exists():
            # Skip if .lrc already exists
            continue
        
        print(f"[{i}/{len(files)}] Processing: {file_path.name}")

        # 1. Get raw info (Tags first, then Filename)
        raw_artist, raw_title = extract_metadata(file_path)
        if not raw_title:
            name = file_path.stem
            if " - " in name:
                raw_artist, raw_title = name.split(" - ", 1)
            else:
                raw_artist, raw_title = "", name

        # 2. Search LRCLIB with the Cleaned strings
        lyrics = get_lyrics_from_lrclib(raw_artist, raw_title)

        if lyrics:
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(lyrics)
            # Sync with Android Media Store
            subprocess.run(["termux-media-scan", str(lrc_path)], capture_output=True)
            print(f"    [✓] Lyrics saved.")
        else:
            print(f"    [✗] Not found.")
        
        # Respect API rate limits
        time.sleep(0.5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    args = parser.parse_args()
    process_folder(args.folder)

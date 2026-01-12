import os
import re
import json
import subprocess
import argparse
import time
import urllib.parse
import sys
from pathlib import Path

# --- CORE FUNCTIONS ---

def clean_query_text(text):
    if not text: return ""
    
    # 1. ATOMIC STRIP: Nukes everything inside (), [], and {}
    text = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', text)
    
    # 2. Standardize all dash types and separators
    text = re.sub(r'[–—−]', '-', text)
    text = text.replace('_', ' ').replace('|', ' ')
    
    # 3. Remove leading track numbers and dots (e.g., "09 - ", "01. ")
    text = re.sub(r'^\d+[\s._-]*', '', text)

    # 4. Aggressive Domain and Quality Strip
    text = re.sub(r'(?i)\b[\w-]+\.(com|net|org|in|me|cc|info|biz|icu)\b', '', text)
    text = re.sub(r'(?i)\b(HD|SD|HQ|4K|2K|1080p|720p|HDRIP|BLURAY)\b', '', text)

    # 5. Filter out specific Contextual Junk
    noise = [
        r'(?i)Official\s+Music\s+Video', r'(?i)Official\s+Video', r'(?i)Lyric\s+Video', 
        r'(?i)Full\s+Audio', r'(?i)League\s+of\s+Legends', r'(?i)Worlds\s+\d{4}', 
        r'(?i)GTA\s+V\s+Radio', r'(?i)Musicfire', r'(?i)Soundtrack', r'(?i)\bOST\b'
    ]
    for pattern in noise:
        text = re.sub(pattern, '', text)

    # 6. Handle features - Strip everything after ft/feat
    text = re.sub(r'(?i)\b(feat|ft|featuring)\b.*$', '', text)
    
    # 7. Final Polish
    text = re.sub(r'\s+', ' ', text)
    return text.strip().strip('-').strip()

def fetch_from_api(artist, title):
    try:
        if not title or len(title) < 3 or '.' in title: 
            return None
        params = urllib.parse.urlencode({'track_name': title, 'artist_name': artist or ''})
        url = f"https://lrclib.net/api/search?{params}"
        result = subprocess.run(["curl", "-s", "-L", "--max-time", "6", url], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            res = json.loads(result.stdout)
            if res:
                return res[0].get('syncedLyrics') or res[0].get('plainLyrics')
    except: pass
    return None

def extract_metadata(file_path):
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_entries", "format_tags=artist,title", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            tags = json.loads(result.stdout).get('format', {}).get('tags', {})
            return tags.get('artist', tags.get('ARTIST', '')), tags.get('title', tags.get('TITLE', ''))
    except: pass
    return "", ""

def get_lyrics_tiered(raw_artist, raw_title, filename_stem):
    c_art, c_tit, c_file = clean_query_text(raw_artist), clean_query_text(raw_title), clean_query_text(filename_stem)
    candidates = []
    if c_tit:
        candidates.append((c_art, c_tit)); candidates.append(("", c_tit))
        if "-" in c_tit:
            p = [i.strip() for i in c_tit.split("-", 1)]
            candidates.append((p[0], p[1])); candidates.append(("", p[1]))
    if c_file:
        candidates.append(("", c_file))
        if "-" in c_file:
            p = [i.strip() for i in c_file.split("-")]
            if len(p) >= 2: candidates.append((p[0], p[1])); candidates.append(("", p[1]))
            candidates.append(("", p[-1]))

    seen = set()
    for art, tit in candidates:
        key = f"{art.lower()}|{tit.lower()}"
        if not tit or len(tit) < 3 or key in seen: continue
        seen.add(key)
        print(f"    [→] Query: {art + ' - ' if art else ''}{tit}")
        res = fetch_from_api(art, tit)
        if res: return res
    return None

def process_folder(folder_path, force=False, retry=False):
    folder = Path(folder_path)
    db_path = folder / ".lyrics.json"
    db = {}
    if db_path.exists():
        try:
            with open(db_path, 'r', encoding='utf-8') as f: db = json.load(f)
        except: pass
    
    files = list(folder.glob("*.mp3"))
    if not files and not db: return {"found": 0, "not_found": 0, "skipped": 0}

    # JSON maintenance
    current_filenames = {f.name for f in files}
    db = {k: v for k, v in db.items() if k in current_filenames}

    stats = {"found": 0, "not_found": 0, "skipped": 0}
    print(f"\n[*] FOLDER: {folder.name} ({len(files)} files)")
    
    for i, file_path in enumerate(files, 1):
        filename, lrc_path = file_path.name, file_path.with_suffix('.lrc')
        state = db.get(filename)
        
        # Logic: re-check Found (1) if file is missing; honor Not Found (0) unless retrying
        should_process = (force) or (retry and state == 0) or (not lrc_path.exists() and state != 0)

        if not should_process:
            stats["skipped"] += 1; continue

        print(f"[{i}/{len(files)}] {filename}")
        meta_art, meta_tit = extract_metadata(file_path)
        lyrics = get_lyrics_tiered(meta_art, meta_tit, file_path.stem)

        if lyrics:
            with open(lrc_path, 'w', encoding='utf-8') as f: f.write(lyrics)
            subprocess.run(["termux-media-scan", str(lrc_path)], capture_output=True)
            db[filename] = 1; stats["found"] += 1; print(f"    [✓] Success!")
        else:
            db[filename] = 0; stats["not_found"] += 1; print(f"    [✗] Failed.")
        
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, separators=(',', ':'), ensure_ascii=False)
        time.sleep(0.4)
    return stats

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recursive Atomic Lyric Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python relyrics.py /sdcard/Music              Process new songs in one folder
  python relyrics.py /sdcard/Music -R           Process all subdirectories recursively
  python relyrics.py /Music/AR /Music/EN -R     Queue multiple root folders
  python relyrics.py /sdcard/Music -r           Retry only songs marked 'not found'
  python relyrics.py /sdcard/Music -f           Force re-download everything
        """
    )
    parser.add_argument("folders", nargs="*", help="Paths to music folders")
    parser.add_argument("-R", "--recursive", action="store_true", help="Crawl all subdirectories for MP3s")
    parser.add_argument("-f", "--force", action="store_true", help="Ignore existing files and index; download everything")
    parser.add_argument("-r", "--retry", action="store_true", help="Retry songs previously saved as 'not found' (0) in index")
    
    args = parser.parse_args()
    if not args.folders:
        parser.print_help(); sys.exit(0)

    queue = []
    for root_folder in args.folders:
        p = Path(root_folder)
        if p.is_dir():
            queue.append(p)
            if args.recursive:
                for sub in p.rglob("*"):
                    if sub.is_dir(): queue.append(sub)

    total_stats = {"found": 0, "not_found": 0, "skipped": 0}
    for folder in queue:
        s = process_folder(folder, force=args.force, retry=args.retry)
        for k in total_stats: total_stats[k] += s[k]

    print(f"\n{'='*30}\nGlobal Summary: Found: {total_stats['found']} | Failed: {total_stats['not_found']} | Skipped: {total_stats['skipped']}\n{'='*30}")

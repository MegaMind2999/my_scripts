#!/usr/bin/env python3
"""
Recursive Atomic Lyric Manager
Fetches and manages synchronized lyrics for MP3 files
"""

import os
import re
import json
import subprocess
import argparse
import time
import urllib.parse
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Set
from dataclasses import dataclass

# --- CONFIGURATION ---

@dataclass
class Config:
    """Configuration constants"""
    API_URL = "https://lrclib.net/api/search"
    API_TIMEOUT = 6
    REQUEST_DELAY = 0.4
    MIN_TITLE_LENGTH = 3
    DB_FILENAME = ".lyrics.json"


# --- CORE FUNCTIONS ---

def clean_query_text(text: str) -> str:
    """
    Clean and normalize text for API queries.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned and normalized text
    """
    if not text:
        return ""
    
    # 1. Remove content in brackets and parentheses
    text = re.sub(r'\([^)]*\)|\[[^\]]*\]|\{[^}]*\}', '', text)
    
    # 2. Normalize separators
    text = re.sub(r'[–—−]', '-', text)
    text = text.replace('_', ' ').replace('|', ' ')
    
    # 3. Remove leading track numbers
    text = re.sub(r'^\d+[\s._-]+', '', text)

    # 4. Remove domains and quality indicators
    text = re.sub(r'(?i)\b[\w-]+\.(com|net|org|in|me|cc|info|biz|icu)\b', '', text)
    text = re.sub(r'(?i)\b(HD|SD|HQ|4K|2K|1080p|720p|HDRIP|BLURAY|WEBDL|WEBRIP)\b', '', text)

    # 5. Remove common noise patterns
    noise_patterns = [
        r'(?i)Official\s+Music\s+Video',
        r'(?i)Official\s+Video',
        r'(?i)Lyric\s+Video',
        r'(?i)Full\s+Audio',
        r'(?i)League\s+of\s+Legends',
        r'(?i)Worlds\s+\d{4}',
        r'(?i)GTA\s+V\s+Radio',
        r'(?i)Musicfire',
        r'(?i)Soundtrack',
        r'(?i)\bOST\b',
        r'(?i)\bRemix\b',
        r'(?i)\bCover\b',
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text)

    # 6. Remove years (1900-2099)
    text = re.sub(r'\b(19|20)\d{2}\b', '', text)

    # 7. Handle features - strip everything after ft/feat
    text = re.sub(r'(?i)\b(feat|ft|featuring)\b.*$', '', text)
    
    # 8. Final cleanup
    text = re.sub(r'\s+', ' ', text)
    text = text.strip().strip('-').strip()
    
    return text


def split_languages(text: str) -> Tuple[str, str]:
    """
    Split text into English and non-English (e.g., Arabic) parts.
    
    Args:
        text: Mixed language text
        
    Returns:
        Tuple of (english_text, non_english_text)
    """
    if not text:
        return "", ""
    
    # English: Latin alphabet, numbers, common punctuation
    english_parts = re.findall(r'[a-zA-Z0-9\s\-\'\.]+', text)
    english = ' '.join(english_parts).strip()
    
    # Non-English: Everything else (Arabic, etc.)
    non_english = re.sub(r'[a-zA-Z0-9\s\-\'\.]+', '', text).strip()
    
    return english, non_english


def fetch_from_api(artist: str, title: str) -> Optional[str]:
    """
    Fetch lyrics from lrclib API.
    
    Args:
        artist: Artist name
        title: Song title
        
    Returns:
        Lyrics text if found, None otherwise
    """
    try:
        # Validate title
        if not title or len(title) < Config.MIN_TITLE_LENGTH or '.' in title:
            return None
        
        # Build API request
        params = urllib.parse.urlencode({
            'track_name': title,
            'artist_name': artist or ''
        })
        url = f"{Config.API_URL}?{params}"
        
        # Execute curl command
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(Config.API_TIMEOUT), url],
            capture_output=True,
            text=True,
            timeout=Config.API_TIMEOUT + 2
        )
        
        if result.returncode != 0 or not result.stdout:
            return None
        
        # Parse response
        response = json.loads(result.stdout)
        if not response:
            return None
        
        # Prefer synced lyrics, fallback to plain
        first_result = response[0]
        return first_result.get('syncedLyrics') or first_result.get('plainLyrics')
        
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception) as e:
        print(f"    [!] API error: {type(e).__name__}")
        return None


def extract_metadata(file_path: Path) -> Tuple[str, str]:
    """
    Extract artist and title metadata from audio file.
    
    Args:
        file_path: Path to audio file
        
    Returns:
        Tuple of (artist, title)
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=artist,title",
            str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            return "", ""
        
        data = json.loads(result.stdout)
        tags = data.get('format', {}).get('tags', {})
        
        # Try both lowercase and uppercase tag names
        artist = tags.get('artist') or tags.get('ARTIST', '')
        title = tags.get('title') or tags.get('TITLE', '')
        
        return artist, title
        
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        return "", ""


def generate_query_candidates(
    raw_artist: str,
    raw_title: str,
    filename_stem: str
) -> List[Tuple[str, str]]:
    """
    Generate list of (artist, title) query candidates in priority order.
    
    Args:
        raw_artist: Raw artist metadata
        raw_title: Raw title metadata
        filename_stem: Filename without extension
        
    Returns:
        List of (artist, title) tuples to try
    """
    c_art = clean_query_text(raw_artist)
    c_tit = clean_query_text(raw_title)
    c_file = clean_query_text(filename_stem)
    
    candidates = []
    
    # Strategy 1: Use metadata title
    if c_tit:
        # Split into English and non-English parts
        eng_tit, non_eng_tit = split_languages(c_tit)
        eng_art, non_eng_art = split_languages(c_art)
        
        # Try full title with artist
        candidates.append((c_art, c_tit))
        
        # Try English parts only
        if eng_tit:
            candidates.append((eng_art, eng_tit))
            candidates.append(("", eng_tit))
        
        # Try non-English parts only
        if non_eng_tit:
            candidates.append((non_eng_art, non_eng_tit))
            candidates.append(("", non_eng_tit))
        
        # Try without artist
        candidates.append(("", c_tit))
        
        # Try splitting on dash
        if "-" in c_tit:
            parts = [p.strip() for p in c_tit.split("-", 1)]
            if len(parts) == 2:
                candidates.append((parts[0], parts[1]))
                candidates.append(("", parts[1]))
                
                # Split each part by language
                eng_p1, non_eng_p1 = split_languages(parts[1])
                if eng_p1:
                    candidates.append(("", eng_p1))
                if non_eng_p1:
                    candidates.append(("", non_eng_p1))
    
    # Strategy 2: Use filename
    if c_file and c_file != c_tit:
        eng_file, non_eng_file = split_languages(c_file)
        
        candidates.append(("", c_file))
        
        # Try English filename only
        if eng_file:
            candidates.append(("", eng_file))
        
        # Try non-English filename only
        if non_eng_file:
            candidates.append(("", non_eng_file))
        
        # Try splitting filename
        if "-" in c_file:
            parts = [p.strip() for p in c_file.split("-")]
            if len(parts) >= 2:
                candidates.append((parts[0], parts[1]))
                candidates.append(("", parts[1]))
                
                # Split by language
                eng_p1, non_eng_p1 = split_languages(parts[1])
                if eng_p1:
                    candidates.append(("", eng_p1))
                if non_eng_p1:
                    candidates.append(("", non_eng_p1))
            
            # Try last part
            if parts[-1]:
                candidates.append(("", parts[-1]))
                eng_last, non_eng_last = split_languages(parts[-1])
                if eng_last:
                    candidates.append(("", eng_last))
                if non_eng_last:
                    candidates.append(("", non_eng_last))
    
    return candidates


def get_lyrics_tiered(
    raw_artist: str,
    raw_title: str,
    filename_stem: str
) -> Optional[str]:
    """
    Attempt to fetch lyrics using multiple query strategies.
    
    Args:
        raw_artist: Raw artist metadata
        raw_title: Raw title metadata
        filename_stem: Filename without extension
        
    Returns:
        Lyrics if found, None otherwise
    """
    candidates = generate_query_candidates(raw_artist, raw_title, filename_stem)
    
    # Deduplicate while preserving order
    seen: Set[str] = set()
    
    for artist, title in candidates:
        # Skip invalid titles
        if not title or len(title) < Config.MIN_TITLE_LENGTH:
            continue
        
        # Deduplicate
        key = f"{artist.lower()}|{title.lower()}"
        if key in seen:
            continue
        seen.add(key)
        
        # Display query
        query_str = f"{artist} - {title}" if artist else title
        print(f"    [→] Query: {query_str}")
        
        # Try API
        result = fetch_from_api(artist, title)
        if result:
            return result
    
    return None


def load_database(db_path: Path) -> Dict[str, int]:
    """Load lyrics database from JSON file."""
    if not db_path.exists():
        return {}
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(f"    [!] Warning: Could not read {db_path.name}, starting fresh")
        return {}


def save_database(db_path: Path, db: Dict[str, int]) -> None:
    """Save lyrics database to JSON file."""
    try:
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, separators=(',', ':'), ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"    [!] Error saving database: {e}")


def cleanup_database(db: Dict[str, int], current_files: Set[str]) -> Dict[str, int]:
    """Remove entries for files that no longer exist."""
    return {k: v for k, v in db.items() if k in current_files}


def process_file(
    file_path: Path,
    db: Dict[str, int],
    force: bool,
    retry: bool
) -> Optional[bool]:
    """
    Process a single audio file.
    
    Args:
        file_path: Path to audio file
        db: Database dictionary
        force: Force redownload
        retry: Retry failed downloads
        
    Returns:
        True if lyrics found, False if not found, None if skipped
    """
    filename = file_path.name
    lrc_path = file_path.with_suffix('.lrc')
    state = db.get(filename)  # None = never processed, 0 = not found, 1 = found
    lrc_exists = lrc_path.exists()
    
    # If .lrc exists but not recorded in database, record it
    if lrc_exists and state != 1:
        db[filename] = 1
        return None  # Skipped but recorded
    
    # Determine if we should process this file
    should_process = (
        force or                                    # Force mode: redownload everything
        (retry and state == 0) or                   # Retry mode: retry previously failed
        (state is None and not lrc_exists) or       # Not in database and no .lrc file
        (state == 1 and not lrc_exists)             # In database as found but .lrc missing
    )
    
    if not should_process:
        return None  # Skipped
    
    # Extract metadata
    meta_artist, meta_title = extract_metadata(file_path)
    
    # Fetch lyrics
    lyrics = get_lyrics_tiered(meta_artist, meta_title, file_path.stem)
    
    if lyrics:
        # Save lyrics file
        try:
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(lyrics)
            
            # Trigger media scan on Android
            subprocess.run(
                ["termux-media-scan", str(lrc_path)],
                capture_output=True,
                timeout=5
            )
            
            db[filename] = 1
            print(f"    [✓] Success!")
            return True
            
        except (IOError, subprocess.TimeoutExpired) as e:
            print(f"    [!] Error saving file: {e}")
            return False
    else:
        db[filename] = 0
        print(f"    [✗] Failed.")
        return False


def process_folder(folder_path: Path, force: bool = False, retry: bool = False) -> Dict[str, int]:
    """
    Process all MP3 files in a folder.
    
    Args:
        folder_path: Path to folder
        force: Force redownload all
        retry: Retry previously failed
        
    Returns:
        Statistics dictionary
    """
    db_path = folder_path / Config.DB_FILENAME
    db = load_database(db_path)
    
    # Find all MP3 files
    files = sorted(folder_path.glob("*.mp3"))
    
    if not files and not db:
        return {"found": 0, "not_found": 0, "skipped": 0}
    
    # Clean up database
    current_filenames = {f.name for f in files}
    db = cleanup_database(db, current_filenames)
    
    # Initialize statistics
    stats = {"found": 0, "not_found": 0, "skipped": 0}
    
    print(f"\n[*] FOLDER: {folder_path.name} ({len(files)} files)")
    
    # Process each file
    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {file_path.name}")
        
        result = process_file(file_path, db, force, retry)
        
        if result is True:
            stats["found"] += 1
        elif result is False:
            stats["not_found"] += 1
        else:  # None = skipped
            stats["skipped"] += 1
        
        # Save database after each file
        save_database(db_path, db)
        
        # Rate limiting
        if result is not None:
            time.sleep(Config.REQUEST_DELAY)
    
    return stats


def collect_folders(root_folders: List[Path], recursive: bool) -> List[Path]:
    """
    Collect all folders to process.
    
    Args:
        root_folders: List of root folder paths
        recursive: Whether to recurse into subdirectories
        
    Returns:
        List of folder paths to process
    """
    queue = []
    
    for root in root_folders:
        if not root.is_dir():
            print(f"[!] Warning: {root} is not a directory, skipping")
            continue
        
        queue.append(root)
        
        if recursive:
            for subdir in sorted(root.rglob("*")):
                if subdir.is_dir():
                    queue.append(subdir)
    
    return queue


# --- MAIN EXECUTION ---

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Recursive Atomic Lyric Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /sdcard/Music              Process new songs in one folder
  %(prog)s /sdcard/Music -R           Process all subdirectories recursively
  %(prog)s /Music/AR /Music/EN -R     Queue multiple root folders
  %(prog)s /sdcard/Music -r           Retry only songs marked 'not found'
  %(prog)s /sdcard/Music -f           Force re-download everything
        """
    )
    
    parser.add_argument(
        "folders",
        nargs="*",
        help="Paths to music folders"
    )
    parser.add_argument(
        "-R", "--recursive",
        action="store_true",
        help="Crawl all subdirectories for MP3s"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Ignore existing files and index; download everything"
    )
    parser.add_argument(
        "-r", "--retry",
        action="store_true",
        help="Retry songs previously saved as 'not found' (0) in index"
    )
    
    args = parser.parse_args()
    
    if not args.folders:
        parser.print_help()
        sys.exit(0)
    
    # Collect folders to process
    root_paths = [Path(f) for f in args.folders]
    queue = collect_folders(root_paths, args.recursive)
    
    if not queue:
        print("[!] No valid folders to process")
        sys.exit(1)
    
    # Process all folders
    total_stats = {"found": 0, "not_found": 0, "skipped": 0}
    
    for folder in queue:
        stats = process_folder(folder, force=args.force, retry=args.retry)
        for key in total_stats:
            total_stats[key] += stats[key]
    
    # Print summary
    print(f"\n{'=' * 40}")
    print(f"Global Summary:")
    print(f"  Found:     {total_stats['found']}")
    print(f"  Failed:    {total_stats['not_found']}")
    print(f"  Skipped:   {total_stats['skipped']}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()
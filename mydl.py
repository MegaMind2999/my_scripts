import os
import argparse
import subprocess
import sys
import glob
import shutil
import re
import time
import json
from pathlib import Path
from datetime import datetime

HISTORY_FILE = "/sdcard/Download/.download_history.json"
QUEUE_FILE = "/sdcard/Download/.download_queue.json"
COOKIES_FILE = "/sdcard/Download/cookies.txt"

def find_deno():
    return shutil.which("deno")

def load_history():
    """Load download history"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_history(history):
    """Save download history"""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[!] Could not save history: {e}")

def add_to_history(url, title, status, file_type="music"):
    """Add download to history"""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in history:
        history[today] = []
    
    history[today].append({
        "url": url,
        "title": title,
        "status": status,
        "type": file_type,
        "timestamp": datetime.now().isoformat()
    })
    
    save_history(history)

def check_duplicate(url):
    """Check if URL was already downloaded"""
    history = load_history()
    for date, entries in history.items():
        for entry in entries:
            if entry.get("url") == url and entry.get("status") == "success":
                return True, entry.get("title", "Unknown")
    return False, None

def check_dependencies():
    """Check if required tools are installed"""
    required = {
        'yt-dlp': 'pip install yt-dlp',
        'aria2c': 'pkg install aria2',
        'ffprobe': 'pkg install ffmpeg',
        'curl': 'pkg install curl'
    }
    
    missing = []
    for tool, install_cmd in required.items():
        if not shutil.which(tool):
            missing.append((tool, install_cmd))
    
    if missing:
        print("[!] Missing required tools:")
        for tool, cmd in missing:
            print(f"    {tool}: {cmd}")
        print("\nInstall missing tools and try again.")
        return False
    return True

def load_queue():
    """Load download queue"""
    try:
        if os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return []

def save_queue(queue):
    """Save download queue"""
    try:
        with open(QUEUE_FILE, 'w') as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        print(f"[!] Could not save queue: {e}")

def search_youtube(query):
    """Search YouTube and return results"""
    print(f"\n[*] Searching for: {query}")
    cmd = [
        "yt-dlp", "--dump-json", "--playlist-end", "10",
        f"ytsearch10:{query}"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        data = json.loads(line)
                        results.append({
                            'title': data.get('title', 'Unknown'),
                            'url': data.get('webpage_url', ''),
                            'duration': data.get('duration', 0),
                            'uploader': data.get('uploader', 'Unknown')
                        })
                    except:
                        pass
            return results
    except Exception as e:
        print(f"[!] Search error: {e}")
    return []

def display_search_results(results):
    """Display search results and let user pick"""
    if not results:
        print("[!] No results found")
        return None
    
    print("\n" + "="*70)
    for i, r in enumerate(results, 1):
        duration = f"{r['duration']//60}:{r['duration']%60:02d}" if r['duration'] else "?"
        title = r['title'][:50] + "..." if len(r['title']) > 50 else r['title']
        print(f"{i}. {title}")
        print(f"   By: {r['uploader']} | Duration: {duration}")
        print()
    print("="*70)
    
    try:
        choice = input("\nSelect (1-10, 'a' for all, or 'q' to cancel): ").strip().lower()
        if choice == 'q':
            return None
        if choice == 'a':
            return [r['url'] for r in results]  # Return all URLs
        idx = int(choice) - 1
        if 0 <= idx < len(results):
            return results[idx]['url']
    except ValueError:
        pass
    
    print("[!] Invalid selection")
    return None

def send_notification(title, content):
    """Send Termux notification"""
    try:
        subprocess.run([
            "termux-notification",
            "--title", title,
            "--content", content,
            "--priority", "high"
        ], capture_output=True)
    except:
        pass

def get_lyrics_from_lrclib(artist, title):
    """Download lyrics from LRCLIB.net API using curl"""
    try:
        artist = re.sub(r'[^\w\s-]', '', artist).strip()
        title = re.sub(r'[^\w\s-]', '', title).strip()
        
        if not artist or not title:
            return None
        
        print(f"[*] Searching LRCLIB for: {artist} - {title}")
        
        import urllib.parse
        url = f"https://lrclib.net/api/search?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
        
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "10", url],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            results = json.loads(result.stdout)
            
            if results and len(results) > 0:
                lyrics_data = results[0]
                
                if 'syncedLyrics' in lyrics_data and lyrics_data['syncedLyrics']:
                    print(f"[+] Found synced lyrics!")
                    return lyrics_data['syncedLyrics']
                elif 'plainLyrics' in lyrics_data and lyrics_data['plainLyrics']:
                    print(f"[+] Found plain lyrics (converting to LRC)")
                    plain = lyrics_data['plainLyrics']
                    lrc_lines = []
                    for i, line in enumerate(plain.split('\n')):
                        timestamp = f"[{i:02d}:00.00]"
                        lrc_lines.append(f"{timestamp}{line}")
                    return "\n".join(lrc_lines)
        
        print(f"[!] No lyrics found")
        return None
    except json.JSONDecodeError:
        print(f"[!] Invalid response from LRCLIB")
        return None
    except Exception as e:
        print(f"[!] LRCLIB error: {e}")
        return None

def extract_metadata_and_download_lyrics(file_path):
    """Extract artist/title from downloaded file and fetch lyrics from LRCLIB"""
    try:
        lrc_path = file_path.rsplit('.', 1)[0] + '.lrc'
        if os.path.exists(lrc_path):
            print(f"[*] Lyrics already exist for {os.path.basename(file_path)}")
            return True
        
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format_tags=artist,title", file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            metadata = json.loads(result.stdout)
            
            tags = metadata.get('format', {}).get('tags', {})
            artist = tags.get('artist', tags.get('ARTIST', ''))
            title = tags.get('title', tags.get('TITLE', ''))
            
            if artist and title:
                lyrics = get_lyrics_from_lrclib(artist, title)
                
                if lyrics:
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(lyrics)
                    print(f"[+] Lyrics saved: {os.path.basename(lrc_path)}")
                    
                    # Index the LRC file so Samsung Music can see it immediately
                    subprocess.run(["termux-media-scan", lrc_path], capture_output=True)
                    print(f"[+] Lyrics indexed for Samsung Music\n")
                    return True
            else:
                print(f"[!] Could not extract metadata from {os.path.basename(file_path)}\n")
        
        return False
    except Exception as e:
        print(f"[!] Error processing {os.path.basename(file_path)}: {e}\n")
        return False

def process_all_songs_for_lyrics(folder):
    """Process all MP3 files in folder and download lyrics for each"""
    mp3_files = glob.glob(os.path.join(folder, "*.mp3"))
    
    if not mp3_files:
        print("[!] No MP3 files found")
        return
    
    print(f"\n[*] Processing {len(mp3_files)} song(s) for lyrics...\n")
    print("=" * 60)
    
    success_count = 0
    for i, mp3_file in enumerate(mp3_files, 1):
        print(f"[{i}/{len(mp3_files)}] {os.path.basename(mp3_file)}")
        if extract_metadata_and_download_lyrics(mp3_file):
            success_count += 1
    
    print("=" * 60)
    print(f"[+] Lyrics download complete: {success_count}/{len(mp3_files)} successful")

def run_command(command, file_to_scan=None, url="", title="", is_music=True):
    try:
        # Run without capturing output so progress is visible
        subprocess.run(command, check=True)
        if file_to_scan and os.path.exists(file_to_scan):
            subprocess.run(["termux-media-scan", file_to_scan], capture_output=True)
        
        # Add to history
        add_to_history(url, title, "success", "music" if is_music else "video")
        
        # Send notification
        content = f"{'Music' if is_music else 'Video'}: {title}"
        send_notification("Download Complete ✓", content)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Error: Download failed.")
        # Check stderr only if available
        if hasattr(e, 'stderr') and e.stderr and "429" in str(e.stderr):
            print("[!] Rate limited (429). Try toggling Airplane Mode or waiting a few minutes.")
        add_to_history(url, title, "failed", "music" if is_music else "video")
        send_notification("Download Failed ✗", title)
        return False

def rename_lyrics_for_samsung(folder):
    """Rename .en.lrc to .lrc and index for Samsung Music"""
    for lrc_file in glob.glob(os.path.join(folder, "*.en.lrc")):
        new_name = lrc_file.replace(".en.lrc", ".lrc")
        try:
            if os.path.exists(new_name):
                os.remove(new_name)
            os.rename(lrc_file, new_name)
            # Index the renamed file
            subprocess.run(["termux-media-scan", new_name], capture_output=True)
            print(f"[*] Lyrics optimized for Samsung Music: {os.path.basename(new_name)}")
        except Exception as e:
            print(f"[!] Rename failed: {e}")

def cleanup_temp_files(folder, keep_lyrics=False):
    extensions = ['*.webp', '*.jpg', '*.png', '*.jpeg', '*.part', '*.ytdl', '*.vtt', '*.srt']
    if not keep_lyrics:
        extensions += ['*.lrc']
    for ext in extensions:
        for file in glob.glob(os.path.join(folder, ext)):
            try: os.remove(file)
            except: pass

def download_subtitles(cmd, subs_option):
    """Add subtitle download options"""
    if subs_option == "auto":
        cmd += ["--write-auto-subs", "--sub-lang", "en"]
    elif subs_option == "all":
        cmd += ["--write-subs", "--all-subs"]
    elif subs_option:
        cmd += ["--write-subs", "--sub-lang", subs_option]
    
    cmd += ["--embed-subs"]
    return cmd

def get_quality_preset(preset):
    """Convert quality preset to format string"""
    presets = {
        "4k": "bestvideo[height<=2160]+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best",
        "720p": "bestvideo[height<=720]+bestaudio/best",
        "480p": "bestvideo[height<=480]+bestaudio/best",
    }
    return presets.get(preset.lower(), "best")

def process_queue(queue_items, parsed_args):
    """Process download queue one by one"""
    total = len(queue_items)
    print(f"\n[*] Processing queue: {total} item(s)\n")
    print("=" * 70)
    
    for i, item in enumerate(queue_items, 1):
        print(f"\n[{i}/{total}] Downloading: {item.get('url', 'Unknown')}")
        
        # Temporarily override args with queue item settings
        original_args = parsed_args.args.copy()
        parsed_args.args = [item['type'], item['url']]
        
        # Download
        download_single(parsed_args)
        
        # Restore original args
        parsed_args.args = original_args
        
        print("-" * 70)
    
    # Clear queue after processing
    save_queue([])
    print("\n[+] Queue processing complete!")

def resume_failed():
    """Resume failed downloads from history"""
    history = load_history()
    failed = []
    
    for date, entries in history.items():
        for entry in entries:
            if entry.get("status") == "failed":
                failed.append(entry)
    
    if not failed:
        print("[*] No failed downloads to resume")
        return
    
    print(f"\n[*] Found {len(failed)} failed download(s)")
    print("=" * 70)
    
    for i, entry in enumerate(failed, 1):
        print(f"{i}. {entry.get('title', 'Unknown')}")
        print(f"   Type: {entry.get('type', 'unknown')} | Date: {entry.get('timestamp', 'unknown')[:10]}")
    
    print("=" * 70)
    
    choice = input("\nResume all? (y/n): ").strip().lower()
    if choice == 'y':
        queue = []
        for entry in failed:
            queue.append({
                'url': entry['url'],
                'type': 'm' if entry.get('type') == 'music' else 'v'
            })
        return queue
    
    return []

def download_single(parsed_args):
    """Main download logic for a single item"""
    first_arg = parsed_args.args[0].lower()
    
    if first_arg == 'u':
        print("[*] Updating engine...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
        return

    is_music = False
    url = ""

    if first_arg == 'm' and len(parsed_args.args) > 1:
        is_music = True
        url = parsed_args.args[1]
    elif first_arg == 'v' and len(parsed_args.args) > 1:
        is_music = False
        url = parsed_args.args[1]
    else:
        url = parsed_args.args[0]
        if "music.youtube.com" in url:
            is_music = True

    # Check for duplicates
    is_dup, dup_title = check_duplicate(url)
    if is_dup and not parsed_args.force:
        print(f"[!] Already downloaded: {dup_title}")
        choice = input("Download again? (y/n): ").strip().lower()
        if choice != 'y':
            return

    target_folder = "/sdcard/Download/"
    os.makedirs(target_folder, exist_ok=True)

    # Base Command
    cmd = [
        "yt-dlp", "--no-mtime", "--force-overwrites",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--downloader", "aria2c", "--downloader-args", "aria2c:-x 16 -s 16",
    ]

    # Feature 18: Cookie support for age-restricted content
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
        print("[*] Using cookies for age-restricted content")

    # Feature 13: Speed limiter
    if parsed_args.speed_limit:
        cmd += ["--limit-rate", parsed_args.speed_limit]
        print(f"[*] Speed limited to: {parsed_args.speed_limit}")

    deno_path = find_deno()
    if deno_path:
        cmd += ["--js-runtimes", f"deno:{deno_path}"]

    if is_music:
        bitrate = "320" if parsed_args.quality == "high" else "96"
        print(f"[*] Music Mode: {bitrate}k MP3 + LRCLIB Lyrics")
        cmd += [
            "-x", "--audio-format", "mp3", "--audio-quality", bitrate,
            "--embed-thumbnail", "--add-metadata", "--embed-metadata",
            "--convert-thumbnails", "jpg", "--sponsorblock-remove", "all",
        ]
        filename_format = "%(title).50s.mp3"
    else:
        # Feature 7: Video quality presets
        if parsed_args.video_quality:
            quality_format = get_quality_preset(parsed_args.video_quality)
            cmd += ["-f", quality_format]
            print(f"[*] Video quality: {parsed_args.video_quality}")
        
        # Feature 8: Subtitle download
        if parsed_args.subs:
            cmd = download_subtitles(cmd, parsed_args.subs)
            print(f"[*] Downloading subtitles: {parsed_args.subs}")
        
        filename_format = "%(title).50s.%(ext)s"

    output_path = os.path.join(target_folder, parsed_args.output if parsed_args.output else filename_format)
    cmd += ["-o", output_path]

    # Site-specific Quality (keep existing logic)
    if not parsed_args.format and not is_music and not parsed_args.video_quality:
        if "tiktok.com" in url:
            cmd += ["-f", "bestvideo+bestaudio/best"] 
        elif any(x in url for x in ["facebook.com", "instagram.com", "twitter.com", "x.com"]):
            cmd += ["-f", "worst"]
        else:
            cmd += ["-f", "best"]

    cmd.append(url)
    
    # Track files before download
    files_before = set(glob.glob(os.path.join(target_folder, "*.mp3")))
    
    # Get title for history
    try:
        title_cmd = ["yt-dlp", "--get-title", url]
        title_result = subprocess.run(title_cmd, capture_output=True, text=True)
        title = title_result.stdout.strip() if title_result.returncode == 0 else "Unknown"
    except:
        title = "Unknown"
    
    success = run_command(cmd, file_to_scan=target_folder, url=url, title=title, is_music=is_music)
    
    if success and is_music:
        files_after = set(glob.glob(os.path.join(target_folder, "*.mp3")))
        new_files = files_after - files_before
        
        if new_files:
            print(f"\n[*] Downloaded {len(new_files)} song(s)")
            process_all_songs_for_lyrics(target_folder)
        else:
            process_all_songs_for_lyrics(target_folder)
        
        rename_lyrics_for_samsung(target_folder)
        cleanup_temp_files(target_folder, keep_lyrics=True)
    else:
        cleanup_temp_files(target_folder, keep_lyrics=False)

def main():
    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description="Enhanced YouTube Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s m URL                          Download music
  %(prog)s v URL                          Download video
  %(prog)s search "song name"             Search and download
  %(prog)s --batch urls.txt               Batch download
  %(prog)s --resume                       Resume failed downloads
  %(prog)s v URL --video-quality 1080p    HD video
  %(prog)s v URL --subs auto              Video with subtitles
  %(prog)s m URL --speed-limit 1M         Limit speed to 1MB/s
  %(prog)s u                              Update yt-dlp
        """
    )
    parser.add_argument("args", nargs="*", help="URL or command (m/v/search/u)")
    parser.add_argument("-F", "--list-formats", action="store_true", help="List available formats")
    parser.add_argument("-f", "--format", help="Manual format selection")
    parser.add_argument("-o", "--output", help="Custom output filename")
    parser.add_argument("-q", "--quality", choices=['low', 'high'], default='high', help="Audio quality (default: high)")
    
    # Feature 7: Video quality presets
    parser.add_argument("--video-quality", choices=['4k', '1080p', '720p', '480p'], 
                       help="Video quality preset")
    
    # Feature 8: Subtitle download
    parser.add_argument("--subs", help="Download subtitles (auto/all/language code)")
    
    # Feature 11: Queue system
    parser.add_argument("--queue", action="store_true", help="Add to download queue")
    
    # Feature 12: Resume failed
    parser.add_argument("--resume", action="store_true", help="Resume failed downloads")
    
    # Feature 13: Speed limiter
    parser.add_argument("--speed-limit", help="Limit download speed (e.g., 1M, 500K)")
    
    # Force re-download
    parser.add_argument("--force", action="store_true", help="Force re-download duplicates")
    
    # Feature 9: Batch download from file
    parser.add_argument("--batch", help="Download URLs from file")

    parsed_args = parser.parse_args()
    
    # Show help if no arguments provided
    if not parsed_args.args and not parsed_args.resume and not parsed_args.batch:
        parser.print_help()
        return
    
    # Feature 12: Resume failed downloads
    if parsed_args.resume:
        resume_queue = resume_failed()
        if resume_queue:
            process_queue(resume_queue, parsed_args)
        return
    
    # Feature 19: Search and download
    if parsed_args.args and parsed_args.args[0].lower() == "search":
        if len(parsed_args.args) < 2:
            print("[!] Usage: script.py search 'query'")
            return
        
        query = " ".join(parsed_args.args[1:])
        results = search_youtube(query)
        selected = display_search_results(results)
        
        if selected:
            # Handle multiple selections (download all)
            if isinstance(selected, list):
                print(f"\n[*] Downloading {len(selected)} result(s)...")
                queue_items = [{'url': url, 'type': 'm'} for url in selected]
                process_queue(queue_items, parsed_args)
            else:
                # Single selection
                parsed_args.args = ['m', selected]
                download_single(parsed_args)
        return
    
    # Feature 9: Batch download from file
    if parsed_args.batch:
        try:
            with open(parsed_args.batch, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            print(f"[*] Found {len(urls)} URL(s) in batch file")
            
            queue_items = []
            for url in urls:
                is_music = "music.youtube.com" in url
                queue_items.append({
                    'url': url,
                    'type': 'm' if is_music else 'v'
                })
            
            process_queue(queue_items, parsed_args)
            return
        except Exception as e:
            print(f"[!] Batch file error: {e}")
            return
    
    if not parsed_args.args:
        return
    
    # Feature 11: Queue system
    if parsed_args.queue:
        queue = load_queue()
        
        first_arg = parsed_args.args[0].lower()
        if first_arg == 'm' and len(parsed_args.args) > 1:
            url = parsed_args.args[1]
            queue.append({'url': url, 'type': 'm'})
        elif first_arg == 'v' and len(parsed_args.args) > 1:
            url = parsed_args.args[1]
            queue.append({'url': url, 'type': 'v'})
        else:
            url = parsed_args.args[0]
            queue.append({'url': url, 'type': 'm' if "music.youtube.com" in url else 'v'})
        
        save_queue(queue)
        print(f"[+] Added to queue ({len(queue)} total)")
        
        choice = input("Process queue now? (y/n): ").strip().lower()
        if choice == 'y':
            process_queue(queue, parsed_args)
        return
    
    # Standard single download
    download_single(parsed_args)
    print(f"\n[+] Task Finished.")

if __name__ == "__main__":
    main()

import os
import argparse
import subprocess
import sys
import glob
import shutil

def find_deno():
    return shutil.which("deno")

def run_command(command, file_to_scan=None):
    try:
        subprocess.run(command, check=True)
        if file_to_scan and os.path.exists(file_to_scan):
            subprocess.run(["termux-media-scan", file_to_scan], capture_output=True)
    except subprocess.CalledProcessError:
        print(f"\n[!] Error: Download failed. TikTok might be blocking the request.")

def cleanup_temp_files(folder, keep_lyrics=False):
    extensions = ['*.webp', '*.jpg', '*.png', '*.jpeg', '*.part', '*.ytdl']
    if not keep_lyrics:
        extensions += ['*.vtt', '*.srt', '*.lrc']
    for ext in extensions:
        for file in glob.glob(os.path.join(folder, ext)):
            try: os.remove(file)
            except: pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("args", nargs="*")
    parser.add_argument("-F", "--list-formats", action="store_true")
    parser.add_argument("-f", "--format", help="Manual format")
    parser.add_argument("-o", "--output", help="Custom filename")
    parser.add_argument("-q", "--quality", choices=['low', 'high'], default='high')

    parsed_args = parser.parse_args()
    if not parsed_args.args: return

    first_arg = parsed_args.args[0].lower()
    if first_arg == 'u':
        print("[*] Updating engine...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
        return

    is_music = False
    if first_arg == 'm' and len(parsed_args.args) > 1:
        is_music = True
        url = parsed_args.args[1]
    else:
        url = parsed_args.args[0]

    target_folder = "/sdcard/Download/"
    os.makedirs(target_folder, exist_ok=True)

    # --- BASE COMMAND ---
    # Added a modern User-Agent to prevent bot detection and impersonation warnings
    cmd = [
        "yt-dlp", "--no-mtime", "--force-overwrites",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "--downloader", "aria2c", "--downloader-args", "aria2c:-x 16 -s 16",
    ]

    deno_path = find_deno()
    if deno_path:
        cmd += ["--js-runtimes", f"deno:{deno_path}"]

    if is_music:
        bitrate = "320" if parsed_args.quality == "high" else "96"
        print(f"[*] Music Mode: {bitrate}k MP3")
        cmd += [
            "-x", "--audio-format", "mp3", "--audio-quality", bitrate,
            "--embed-thumbnail", "--add-metadata", "--embed-metadata",
            "--convert-thumbnails", "jpg", "--sponsorblock-remove", "all",
            "--write-subs", "--write-auto-subs", "--convert-subs", "lrc",
            "--sub-langs", "all,-live_chat",
        ]
        filename_format = "%(title).50s.mp3"
    else:
        filename_format = "%(title).50s.%(ext)s"

    output_path = os.path.join(target_folder, parsed_args.output if parsed_args.output else filename_format)
    cmd += ["-o", output_path]

    # --- TIKTOK NO-WATERMARK LOGIC ---
    if parsed_args.list_formats:
        run_command(["yt-dlp", "-F", url])
        return

    if parsed_args.format:
        cmd += ["-f", parsed_args.format]
    elif not is_music:
        if "tiktok.com" in url:
            print("[*] TikTok: Targeting NO-WATERMARK stream...")
            # We avoid 'worst' here. 'bestvideo+bestaudio' or just 'best'
            # usually fetches the raw API source without the watermark overlay.
            cmd += ["-f", "bestvideo+bestaudio/best"]
        elif any(x in url for x in ["facebook.com", "fb.watch", "instagram.com", "twitter.com", "x.com"]):
            cmd += ["-f", "worst"]
        elif "youtube.com" in url or "youtu.be" in url or "googlevideo" in url:
            cmd += ["-f", "134+139/bestvideo[height<=360]+bestaudio/best"]
        else:
            cmd += ["-f", "best"]

    cmd.append(url)
    run_command(cmd, file_to_scan=target_folder)
    cleanup_temp_files(target_folder, keep_lyrics=is_music)
    print(f"[+] Task Finished.")

if __name__ == "__main__":
    main()

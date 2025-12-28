import os
import argparse
import subprocess
import sys
import glob
import re

def run_command(command, file_to_scan=None):
    try:
        subprocess.run(command, check=True)
        if file_to_scan and os.path.exists(file_to_scan):
            subprocess.run(["termux-media-scan", file_to_scan], capture_output=True)
    except subprocess.CalledProcessError:
        print(f"\n[!] Error: Download failed. This can happen with very restricted videos or network issues.")

def update_dependencies():
    print("[*] Updating yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    print("[+] Update complete!")

def cleanup_temp_files(folder):
    extensions = ['*.webp', '*.jpg', '*.png', '*.jpeg', '*.part', '*.ytdl']
    for ext in extensions:
        for file in glob.glob(os.path.join(folder, ext)):
            try: os.remove(file)
            except: pass

def main():
    parser = argparse.ArgumentParser(description="Termux Universal Downloader (Fixed for Long Filenames)")
    parser.add_argument("args", nargs="*", help="Format: [m/u] URL")
    parser.add_argument("-F", "--list-formats", action="store_true")
    parser.add_argument("-f", "--format", help="Manual format code")
    parser.add_argument("-o", "--output", help="Custom filename")
    parser.add_argument("-q", "--quality", choices=['low', 'high'], default='high')
    
    parsed_args = parser.parse_args()
    if not parsed_args.args: return

    first_arg = parsed_args.args[0].lower()

    if first_arg == 'u':
        update_dependencies()
        return

    is_music = False
    if first_arg == 'm' and len(parsed_args.args) > 1:
        is_music = True
        url = parsed_args.args[1]
    else:
        url = parsed_args.args[0]

    target_folder = "/sdcard/Download/"
    os.makedirs(target_folder, exist_ok=True)

    # Base Command
    cmd = [
        "yt-dlp", "--no-mtime", "--force-overwrites",
        "--downloader", "aria2c", "--downloader-args", "aria2c:-x 16 -s 16 -k 1M",
        "--referer", "https://www.google.com/"
    ]

    # --- FIX: TRUNCATE LONG FILENAMES ---
    # We tell yt-dlp to limit the title length to 50 characters to avoid "File name too long" error
    if is_music:
        bitrate = "320" if parsed_args.quality == "high" else "96"
        print(f"[*] Music Mode: {bitrate}k MP3")
        cmd += [
            "-x", "--audio-format", "mp3", "--audio-quality", bitrate,
            "--embed-thumbnail", "--add-metadata", "--embed-metadata",
            "--convert-thumbnails", "jpg", "--sponsorblock-remove", "all"
        ]
        filename_format = "%(title).50s.mp3"
    else:
        filename_format = "%(title).50s.%(ext)s"

    # Custom Output Override
    if parsed_args.output:
        name = parsed_args.output if "." in parsed_args.output else f"{parsed_args.output}.%(ext)s"
        cmd += ["-o", os.path.join(target_folder, name)]
    else:
        cmd += ["-o", os.path.join(target_folder, filename_format)]

    # Format Logic
    if parsed_args.list_formats:
        run_command(["yt-dlp", "-F", url])
        return

    if parsed_args.format:
        cmd += ["-f", parsed_args.format]
    elif not is_music:
        if any(x in url for x in ["facebook.com", "fb.watch", "instagram.com", "twitter.com", "x.com"]):
            print("[*] Social Media: Lowest Quality Default")
            cmd += ["-f", "worst"]
        elif "youtube.com" in url or "youtu.be" in url:
            print("[*] YouTube: 360p Default")
            cmd += ["-f", "134+139/bestvideo[height<=360]+bestaudio/best"]
        else:
            cmd += ["-f", "best"]

    cmd.append(url)
    run_command(cmd, file_to_scan=target_folder)
    
    cleanup_temp_files(target_folder)
    print(f"[+] Process Finished.")

if __name__ == "__main__":
    main()

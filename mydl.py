import os
import argparse
import subprocess
import sys

def run_command(command, file_to_scan=None):
    try:
        subprocess.run(command, check=True)
        # Scan folder so Android Media Store sees the new files instantly
        if file_to_scan and os.path.exists(file_to_scan):
            subprocess.run(["termux-media-scan", file_to_scan], capture_output=True)
    except subprocess.CalledProcessError:
        print(f"\n[!] Error: Command failed. If it's a speed error, run: pkg install aria2")

def update_dependencies():
    print("[*] Updating yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    print("[+] Update complete!")

def main():
    parser = argparse.ArgumentParser(description="Termux Master Downloader (MP3 Optimized)")
    parser.add_argument("args", nargs="*", help="Format: [m/u] URL")
    parser.add_argument("-F", "--list-formats", action="store_true")
    parser.add_argument("-f", "--format", help="Manual format code")
    parser.add_argument("-o", "--output", help="Custom filename")
    parser.add_argument("-q", "--quality", choices=['low', 'high'], default='high', 
                        help="Music quality: low (96k-128k) or high (320k)")
    
    parsed_args = parser.parse_args()
    
    if not parsed_args.args:
        parser.print_help()
        return

    first_arg = parsed_args.args[0].lower()

    # --- COMMAND: d u (Update) ---
    if first_arg == 'u':
        update_dependencies()
        return

    # --- COMMAND: d m (Music) ---
    is_music = False
    if first_arg == 'm' and len(parsed_args.args) > 1:
        is_music = True
        url = parsed_args.args[1]
    else:
        url = parsed_args.args[0]

    target_folder = "/sdcard/Download/"
    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)

    # Base Command + Force Overwrite (to fix "already downloaded" big files)
    cmd = [
        "yt-dlp", "--no-mtime", "--force-overwrites",
        "--downloader", "aria2c", 
        "--downloader-args", "aria2c:-x 16 -s 16 -k 1M",
        "--referer", "https://www.google.com/"
    ]

    if is_music:
        # MP3 Bitrate Logic
        # '96' is very small, '320' is large.
        bitrate = "320" if parsed_args.quality == "high" else "96"
        print(f"[*] Music Mode: {bitrate}k MP3 + Small Art + Metadata")
        
        cmd += [
            "-x", "--audio-format", "mp3", "--audio-quality", bitrate,
            "--embed-thumbnail", "--add-metadata", "--embed-metadata",
            "--convert-thumbnails", "jpg",  # JPG is 10x smaller than PNG for album art
            "--write-auto-subs", "--embed-subs", "--sponsorblock-remove", "all"
        ]
        ext = "mp3"
    else:
        ext = "%(ext)s"

    # Filename Template
    name = parsed_args.output if parsed_args.output else f"%(title)s.{ext}"
    if "." not in name and not ext.startswith("%"): name = f"{name}.{ext}"
    
    output_path = os.path.join(target_folder, name)
    cmd += ["-o", output_path]

    # Formats
    if parsed_args.list_formats:
        run_command(["yt-dlp", "-F", url])
        return

    if parsed_args.format:
        cmd += ["-f", parsed_args.format]
    elif not is_music:
        if "youtube.com" in url or "youtu.be" in url:
            cmd += ["-f", "134+139/bestvideo[height<=360]+bestaudio/best"]
        elif any(x in url for x in ["facebook.com", "fb.watch", "instagram.com"]):
            cmd += ["-f", "worst"]
        elif "tiktok.com" in url:
            cmd += ["-f", "best"]

    cmd.append(url)
    run_command(cmd, file_to_scan=target_folder)
    print(f"[+] Process Finished. Saved to: {target_folder}")

if __name__ == "__main__":
    main()

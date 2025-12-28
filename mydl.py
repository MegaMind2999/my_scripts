import os
import argparse
import subprocess
import sys
import glob

def run_command(command, file_to_scan=None):
    try:
        subprocess.run(command, check=True)
        # Scan folder so Android Media Store sees the new files instantly
        if file_to_scan and os.path.exists(file_to_scan):
            subprocess.run(["termux-media-scan", file_to_scan], capture_output=True)
    except subprocess.CalledProcessError:
        print(f"\n[!] Error: Command failed. Try updating: d u")

def update_dependencies():
    print("[*] Updating yt-dlp...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])
    print("[+] Update complete!")

def cleanup_temp_files(folder):
    # Removes leftover images after embedding
    extensions = ['*.webp', ['*.jpg'], ['*.png'], ['*.jpeg']]
    for ext in extensions:
        for file in glob.glob(os.path.join(folder, str(ext))):
            try: os.remove(file)
            except: pass

def main():
    parser = argparse.ArgumentParser(description="Termux Universal Downloader (YT/FB/TT/IG/TW)")
    parser.add_argument("args", nargs="*", help="Format: [m/u] URL")
    parser.add_argument("-F", "--list-formats", action="store_true")
    parser.add_argument("-f", "--format", help="Manual format code")
    parser.add_argument("-o", "--output", help="Custom filename")
    parser.add_argument("-q", "--quality", choices=['low', 'high'], default='high')
    
    parsed_args = parser.parse_args()
    if not parsed_args.args: return

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
    os.makedirs(target_folder, exist_ok=True)

    # Base Command
    cmd = [
        "yt-dlp", "--no-mtime", "--force-overwrites",
        "--downloader", "aria2c", "--downloader-args", "aria2c:-x 16 -s 16 -k 1M",
        "--referer", "https://www.google.com/"
    ]

    if is_music:
        bitrate = "320" if parsed_args.quality == "high" else "96"
        print(f"[*] Music Mode: {bitrate}k MP3 + Art + Metadata")
        cmd += [
            "-x", "--audio-format", "mp3", "--audio-quality", bitrate,
            "--embed-thumbnail", "--add-metadata", "--embed-metadata",
            "--convert-thumbnails", "jpg", "--sponsorblock-remove", "all"
        ]
        ext = "mp3"
    else:
        ext = "%(ext)s"

    # Filename
    name = parsed_args.output if parsed_args.output else f"%(title)s.{ext}"
    if "." not in name and not ext.startswith("%"): name = f"{name}.{ext}"
    cmd += ["-o", os.path.join(target_folder, name)]

    # Format Logic
    if parsed_args.list_formats:
        run_command(["yt-dlp", "-F", url])
        return

    if parsed_args.format:
        cmd += ["-f", parsed_args.format]
    elif not is_music:
        # Defaults
        if "youtube.com" in url or "youtu.be" in url:
            print("[*] YouTube: 360p Default")
            cmd += ["-f", "134+139/bestvideo[height<=360]+bestaudio/best"]
        elif any(x in url for x in ["facebook.com", "fb.watch", "instagram.com", "twitter.com", "x.com"]):
            print("[*] Social Media (FB/IG/TW): Lowest Quality Default")
            cmd += ["-f", "worst"]
        elif "tiktok.com" in url:
            cmd += ["-f", "best"]

    cmd.append(url)
    run_command(cmd, file_to_scan=target_folder)
    
    # Final Cleanup
    cleanup_temp_files(target_folder)
    print(f"[+] Process Finished. Saved to: {target_folder}")

if __name__ == "__main__":
    main()

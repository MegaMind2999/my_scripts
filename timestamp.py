import os
import json
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

def is_termux():
    """Check if running in Termux environment"""
    return os.path.exists('/data/data/com.termux/files')

def trigger_media_scan(file_path):
    """Trigger Android media scan for a file"""
    if not is_termux():
        return False
    
    try:
        # Use termux-media-scan if available
        result = subprocess.run(
            ['termux-media-scan', file_path],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback: use am broadcast
        try:
            subprocess.run([
                'am', 'broadcast',
                '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                '-d', f'file://{file_path}'
            ], capture_output=True, timeout=5)
            return True
        except:
            return False

def scan_directory_media(directory):
    """Scan entire directory for media indexing"""
    if not is_termux():
        return
    
    print("\n📱 Termux environment detected!")
    print("🔄 Triggering media index update...")
    
    try:
        # Try termux-media-scan for directory
        result = subprocess.run(
            ['termux-media-scan', '-r', directory],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            print("✅ Media index update triggered successfully!")
        else:
            print("⚠️  Media scan may require manual refresh in Samsung Music")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("⚠️  termux-media-scan not available")
        print("💡 Install with: pkg install termux-api")
        print("💡 Or manually refresh Samsung Music library")

def validate_audio_file(file_path):
    """Check if file is a valid audio file"""
    audio_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', 
                       '.opus', '.wma', '.alac', '.ape', '.wv'}
    return Path(file_path).suffix.lower() in audio_extensions

def main():
    parser = argparse.ArgumentParser(
        description="Export or Import File Timestamps with Media Indexing Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Export:  python script.py /path/to/music
  Import:  python script.py /path/to/music music_timestamps.json
  
Features:
  - Auto-detects Termux environment
  - Triggers Android media scanner for audio files
  - Uses folder name in JSON filename
  - Validates audio files for music apps
        """
    )
    parser.add_argument("path", help="Path to the folder containing files")
    parser.add_argument("json", nargs="?", help="Optional: Path to timestamps JSON to IMPORT")
    parser.add_argument("--skip-scan", action="store_true", 
                       help="Skip media scanning even in Termux")
    parser.add_argument("--audio-only", action="store_true",
                       help="Only process audio files")
    
    args = parser.parse_args()
    target_dir = os.path.abspath(args.path)
    
    if not os.path.exists(target_dir):
        print(f"❌ Error: Directory '{target_dir}' not found.")
        return 1
    
    # Get folder name for JSON filename
    folder_name = os.path.basename(target_dir.rstrip(os.sep))
    if not folder_name:  # Root directory case
        folder_name = "root"
    
    # --- IMPORT MODE ---
    if args.json:
        if not os.path.exists(args.json):
            print(f"❌ Error: JSON file '{args.json}' not found.")
            return 1
        
        with open(args.json, "r") as f:
            data = json.load(f)
        
        # Handle both old and new JSON formats
        if "timestamps" in data and isinstance(data["timestamps"], dict):
            # New format with metadata
            timestamp_data = data["timestamps"]
            if "metadata" in data:
                print(f"📋 Metadata:")
                print(f"   Exported: {data['metadata'].get('exported_at', 'Unknown')}")
                print(f"   From: {data['metadata'].get('directory', 'Unknown')}")
                print(f"   Total files: {data['metadata'].get('total_files', 0)}")
                print(f"   Audio files: {data['metadata'].get('audio_files', 0)}")
        else:
            # Old format - data is directly the timestamps dict
            timestamp_data = data
        
        print(f"\n📂 Restoring timestamps in: {target_dir}")
        print(f"📄 From: {args.json}\n")
        
        restored = 0
        missing = 0
        audio_files = []
        
        for rel_path, times in timestamp_data.items():
            full_path = os.path.join(target_dir, rel_path)
            
            if os.path.exists(full_path):
                # Restore timestamps
                os.utime(full_path, (times[0], times[1]))
                
                # Track audio files for media scanning
                if validate_audio_file(full_path):
                    audio_files.append(full_path)
                
                restored += 1
                print(f"✅ Restored: {rel_path}")
            else:
                missing += 1
                print(f"❌ Missing: {rel_path}")
        
        print(f"\n📊 Summary: {restored} restored, {missing} missing")
        
        # Trigger media scan if in Termux and audio files were restored
        if audio_files and not args.skip_scan:
            print(f"\n🎵 Found {len(audio_files)} audio files")
            scan_directory_media(target_dir)
        
        return 0
    
    # --- EXPORT MODE ---
    else:
        json_filename = f"{folder_name}_timestamps.json"
        json_out = os.path.join(target_dir, json_filename)
        
        print(f"📂 Exporting timestamps from: {target_dir}")
        print(f"💾 Output: {json_filename}\n")
        
        timestamp_data = {}
        audio_count = 0
        
        for root, _, files in os.walk(target_dir):
            for name in files:
                # Skip the timestamp JSON itself
                if name.endswith("_timestamps.json"):
                    continue
                
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, target_dir)
                
                # Skip if audio-only mode and not an audio file
                if args.audio_only and not validate_audio_file(full_path):
                    continue
                
                try:
                    stat = os.stat(full_path)
                    timestamp_data[rel_path] = [stat.st_atime, stat.st_mtime]
                    
                    is_audio = validate_audio_file(full_path)
                    if is_audio:
                        audio_count += 1
                        print(f"🎵 {rel_path}")
                    else:
                        print(f"📄 {rel_path}")
                        
                except OSError as e:
                    print(f"⚠️  Skipped (error): {rel_path} - {e}")
        
        # Write JSON with metadata
        output_data = {
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "directory": target_dir,
                "total_files": len(timestamp_data),
                "audio_files": audio_count,
                "platform": "termux" if is_termux() else "standard"
            },
            "timestamps": timestamp_data
        }
        
        with open(json_out, "w") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n✅ Success!")
        print(f"📊 Exported {len(timestamp_data)} files ({audio_count} audio)")
        print(f"💾 Saved to: {json_out}")
        
        if is_termux() and audio_count > 0:
            print(f"\n💡 Tip: When restoring, media scanner will auto-update Samsung Music")
        
        return 0

if __name__ == "__main__":
    sys.exit(main())

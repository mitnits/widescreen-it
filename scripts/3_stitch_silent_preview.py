import os
import glob
import subprocess
import sys

# Load Config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")
OUTPUT_FILE = os.path.join(PROJECT_WORKSPACE, "demo_preview.mp4")

def get_duration(file_path):
    """Returns the precise duration of a video file in seconds."""
    cmd = [
        FFPROBE_BIN, "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        file_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except:
        return 0.0

def main():
    print("--- Silent Preview Stitcher ---")
    
    # 1. Find all rendered chunks
    # Pattern: remastered_000_00001.mp4, etc.
    search_pattern = os.path.join(COMFY_OUTPUT_DIR, "remastered_*.mp4")
    files = sorted(glob.glob(search_pattern))
    
    if not files:
        print("No remastered files found in output directory!")
        return

    # 2. Filter and Sort logic
    # We map index -> filename to ensure we have a continuous sequence
    valid_chunks = []
    expected_index = 0
    
    for f in files:
        fname = os.path.basename(f)
        try:
            # Extract index from "remastered_012_00001.mp4" -> 12
            parts = fname.split('_')
            idx = int(parts[1])
            
            if idx == expected_index:
                valid_chunks.append(f)
                expected_index += 1
            elif idx > expected_index:
                # We hit a gap! (e.g. have 0,1,2 ... missing 3 ... found 4)
                print(f"   [Stop] Missing Chunk {expected_index}. Stitching 0 to {expected_index-1}.")
                break
        except:
            continue

    count = len(valid_chunks)
    print(f"   Found {count} sequential chunks to stitch.")
    if count < 2:
        print("   Need at least 2 chunks to stitch.")
        return

    # 3. Build the XFADE Filter Graph
    # Logic: 
    # [0][1]xfade=duration=1:offset=8.8[v1];
    # [v1][2]xfade=duration=1:offset=17.6[v2]; ...
    
    inputs = []
    filter_chain = ""
    current_offset = 0.0
    last_output_pad = "[0:v]" # Start with first video stream
    
    print("   Calculating offsets...")
    
    for i, chunk_path in enumerate(valid_chunks):
        inputs.extend(["-i", chunk_path])
        
        if i == 0:
            duration = get_duration(chunk_path)
            # The next fade starts at: Duration - Overlap
            current_offset += (duration - OVERLAP)
            continue
            
        # For chunks 1..N
        duration = get_duration(chunk_path)
        
        prev_pad = last_output_pad if i == 1 else f"[v{i-1}]"
        next_pad = f"[v{i}]"
        
        # Determine transition effect (default: fade)
        transition = "fade" 
        
        filter_chain += f"{prev_pad}[{i}:v]xfade=transition={transition}:duration={OVERLAP}:offset={current_offset:.3f}{next_pad};"
        
        # Advance offset for next clip
        current_offset += (duration - OVERLAP)
        last_output_pad = next_pad

    # Remove trailing semicolon
    filter_chain = filter_chain.rstrip(';')

    # 4. Execute FFmpeg
    print(f"   Rendering to: {OUTPUT_FILE}")
    
    cmd = [FFMPEG_BIN, "-y"] + inputs + [
        "-filter_complex", filter_chain,
        "-map", last_output_pad, # Map the final video pad
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an", # No Audio
        OUTPUT_FILE
    ]
    
    # Run it
    subprocess.run(cmd)
    print("\n   Done! check demo_preview.mp4")

if __name__ == "__main__":
    main()


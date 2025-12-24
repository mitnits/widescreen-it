import os
import subprocess
import glob
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")
LOCK_OVERLAP = OVERLAP 

AUDIO_FILE = os.path.join(PROJECT_WORKSPACE, "02_Audio", "master_audio.m4a")
TEMP_VIDEO = os.path.join(PROJECT_WORKSPACE, "temp_stitch_silent.mp4")
OUTPUT_FILE = os.path.join(PROJECT_WORKSPACE, "Final_Pixel_Perfect.mp4")

def get_duration(file_path):
    cmd = [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except: return 0.0

def main():
    print("--- 3. STITCH (PIXEL-LOCK + WMP FIX) ---")
    
    # 1. GATHER FILES
    ai_chunks = sorted(glob.glob(os.path.join(COMFY_OUTPUT_DIR, "remastered_*.mp4")))
    if not ai_chunks:
        print("ERROR: No remastered chunks found.")
        return
        
    print(f"   Found {len(ai_chunks)} chunks.")
    print(f"   Locking Overlap to: {LOCK_OVERLAP}s")

    # 2. CALCULATE DURATION
    first_chunk_dur = get_duration(ai_chunks[0])
    step_duration = first_chunk_dur - LOCK_OVERLAP
    
    print(f"   Chunk Duration: {first_chunk_dur:.2f}s")
    print(f"   Step Duration:  {step_duration:.2f}s")

    # 3. BUILD FILTER CHAIN
    inputs = []
    filter_chain = ""
    last_stream = "0:v"
    current_offset = step_duration

    for f in ai_chunks:
        inputs.extend(["-i", f])

    for i in range(1, len(ai_chunks)):
        next_stream = f"{i}:v"
        out_label = f"v{i}" if i < len(ai_chunks) - 1 else "vout"
        filter_chain += f"[{last_stream}][{next_stream}]xfade=transition=fade:duration={LOCK_OVERLAP}:offset={current_offset}[{out_label}];"
        last_stream = out_label
        current_offset += step_duration

    # 4. FIRST PASS: STITCH TO TEMP
    print("\n   [Pass 1] Stitching...")
    cmd_pass1 = [
        FFMPEG_BIN, "-y"
    ] + inputs + [
        "-filter_complex", filter_chain.rstrip(";"),
        "-map", "[vout]",
        
        # FIX 1: Force standard pixel format
        "-c:v", "libx264", "-pix_fmt", "yuv420p", 
        "-preset", "medium", "-crf", "18",
        TEMP_VIDEO
    ]
    subprocess.run(cmd_pass1)

    # 5. SECOND PASS: AUDIO SYNC
    video_dur = get_duration(TEMP_VIDEO)
    audio_dur = get_duration(AUDIO_FILE)
    
    print(f"\n   [Sync Check]")
    print(f"   Stitched Video: {video_dur:.2f}s")
    print(f"   Master Audio:   {audio_dur:.2f}s")
    
    pts_factor = audio_dur / video_dur
    print(f"   Correction: {pts_factor:.4f}x")

    print("\n   [Pass 2] Syncing...")
    cmd_pass2 = [
        FFMPEG_BIN, "-y",
        "-i", TEMP_VIDEO,
        "-i", AUDIO_FILE,
        "-filter_complex", f"[0:v]setpts=PTS*{pts_factor}[vfinal]",
        "-map", "[vfinal]",
        "-map", "1:a",
        
        # FIX 2: Force standard pixel format (Final Output)
        "-c:v", "libx264", "-pix_fmt", "yuv420p", 
        "-preset", "slow", "-crf", "16",
        "-shortest",
        OUTPUT_FILE
    ]
    subprocess.run(cmd_pass2)
    
    print(f"\nDONE! {OUTPUT_FILE}")
    if os.path.exists(TEMP_VIDEO): os.remove(TEMP_VIDEO)

if __name__ == "__main__":
    main()

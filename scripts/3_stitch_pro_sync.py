import os
import subprocess
import glob
import statistics
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")
ORIG_CHUNK_DIR = os.path.join(PROJECT_WORKSPACE, "01_Chunks")
AUDIO_FILE = os.path.join(PROJECT_WORKSPACE, "02_Audio", "master_audio.m4a")
OUTPUT_FILE = os.path.join(PROJECT_WORKSPACE, "Final_Output.mp4")

def get_duration(file_path):
    cmd = [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except: return 0.0

def main():
    print("--- 3. STITCH & SYNC ---")
    
    t_audio = get_duration(AUDIO_FILE)
    ai_chunks = sorted(glob.glob(os.path.join(COMFY_OUTPUT_DIR, "remastered_*.mp4")))
    orig_chunks = sorted(glob.glob(os.path.join(ORIG_CHUNK_DIR, "chunk_*.mp4")))
    
    if not ai_chunks: return

    # Sync Logic
    t_tail = get_duration(orig_chunks[-1])
    body_durations = [get_duration(c) for c in ai_chunks[:-1]]
    avg_body = statistics.mean(body_durations)
    
    target_body = t_audio - t_tail
    n_minus_1 = len(ai_chunks) - 1
    step_duration = target_body / n_minus_1
    calc_overlap = avg_body - step_duration
    
    print(f"   Audio: {t_audio}s | Tail: {t_tail}s")
    print(f"   Calculated Overlap: {calc_overlap:.4f}s")

    inputs = []
    filter_chain = ""
    last_stream = "0:v"
    current_offset = avg_body - calc_overlap

    for f in ai_chunks: inputs.extend(["-i", f])

    for i in range(1, len(ai_chunks)):
        next_stream = f"{i}:v"
        out_label = f"v{i}" if i < len(ai_chunks) - 1 else "vout"
        filter_chain += f"[{last_stream}][{next_stream}]xfade=transition=fade:duration={calc_overlap:.4f}:offset={current_offset:.4f}[{out_label}];"
        last_stream = out_label
        current_offset += (avg_body - calc_overlap)

    cmd = [
        FFMPEG_BIN] + inputs + ["-i", AUDIO_FILE, 
        "-filter_complex", filter_chain.rstrip(";"), 
        "-map", "[vout]", "-map", f"{len(ai_chunks)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
        "-t", str(t_audio), "-y", OUTPUT_FILE
    ]
    
    subprocess.run(cmd)
    print(f"   Done: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()


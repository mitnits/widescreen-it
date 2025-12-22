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
    print("--- 3. STITCH & SYNC (SPEED NORMALIZED) ---")
    
    t_audio = get_duration(AUDIO_FILE)
    ai_chunks = sorted(glob.glob(os.path.join(COMFY_OUTPUT_DIR, "remastered_*.mp4")))
    orig_chunks = sorted(glob.glob(os.path.join(ORIG_CHUNK_DIR, "chunk_*.mp4")))
    
    if len(ai_chunks) != len(orig_chunks):
        print(f"WARNING: Mismatch! AI has {len(ai_chunks)} chunks, Original has {len(orig_chunks)}.")
        # Proceeding anyway, but trimming to the shorter list
        min_len = min(len(ai_chunks), len(orig_chunks))
        ai_chunks = ai_chunks[:min_len]
        orig_chunks = orig_chunks[:min_len]

    # 1. Calculate Target "Body" Duration
    t_tail_true = get_duration(orig_chunks[-1])
    target_body_duration = t_audio - t_tail_true
    
    # 2. Get Average Original Chunk Length (The "Correct" Length)
    # We trust the INPUT length, not the AI output length.
    body_orig_durations = [get_duration(c) for c in orig_chunks[:-1]]
    avg_orig_len = statistics.mean(body_orig_durations)
    
    # 3. Solve for Overlap based on ORIGINAL length
    # (N-1) * (OrigLen - Overlap) = TargetBody
    n_minus_1 = len(ai_chunks) - 1
    step_duration = target_body_duration / n_minus_1
    calc_overlap = avg_orig_len - step_duration
    
    print(f"   Audio: {t_audio:.2f}s | Tail: {t_tail_true:.2f}s")
    print(f"   Avg Original Chunk: {avg_orig_len:.2f}s")
    print(f"   Required Step: {step_duration:.2f}s")
    print(f"   Calculated Overlap: {calc_overlap:.4f}s")

    if calc_overlap < 0:
        print("CRITICAL ERROR: Even using original speeds, the chunks are too short.")
        return

    # 4. Construct Filter Chain with SPEED CORRECTION
    # We verify the AI chunk duration vs Original Chunk duration
    # If AI is 6.5s and Original is 9.8s, we apply setpts to stretch AI to 9.8s.
    
    inputs = []
    filter_chain = ""
    last_stream = "0:v"
    
    # We set the initial offset
    current_offset = step_duration

    # Add inputs
    for f in ai_chunks:
        inputs.extend(["-i", f])

    # We need to normalize every chunk speed first? 
    # Actually, XFADE is tricky with setpts. 
    # Strategy: We assume all AI chunks need to be normalized to 'avg_orig_len'.
    # We calculate the stretch factor.
    
    ai_body_dur = statistics.mean([get_duration(c) for c in ai_chunks[:-1]])
    stretch_factor = avg_orig_len / ai_body_dur
    print(f"   AI Speed Correction Factor: {stretch_factor:.2f}x (Slowing down video to match audio)")

    # Build the complex filter
    # Chunk 0 is the base.
    # [0:v]setpts=PTS*Factor[v0_slow];
    
    filter_chain += f"[0:v]setpts=PTS*{stretch_factor}[stream0];"
    last_stream = "stream0"

    for i in range(1, len(ai_chunks)):
        next_input = f"{i}:v"
        slowed_label = f"stream{i}"
        
        # 1. Slow down the input
        filter_chain += f"[{next_input}]setpts=PTS*{stretch_factor}[{slowed_label}];"
        
        # 2. XFade the previous stream with this new slowed stream
        out_label = f"v_out_{i}" if i < len(ai_chunks) - 1 else "vout"
        
        filter_chain += f"[{last_stream}][{slowed_label}]xfade=transition=fade:duration={calc_overlap:.4f}:offset={current_offset:.4f}[{out_label}];"
        
        last_stream = out_label
        current_offset += step_duration

    # 5. Final Command
    cmd = [
        FFMPEG_BIN] + inputs + ["-i", AUDIO_FILE, 
        "-filter_complex", filter_chain.rstrip(";"), 
        "-map", "[vout]", "-map", f"{len(ai_chunks)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
        "-t", str(t_audio), "-y", OUTPUT_FILE
    ]
    
    print("   Rendering...")
    subprocess.run(cmd)
    print(f"   Done: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()


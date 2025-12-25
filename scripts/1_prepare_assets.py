import os
import subprocess
import json
import shutil
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

# =========================================================
# CONFIGURATION
# =========================================================
TARGET_FPS = 16 
SAFETY_SHAVE = 8  
# =========================================================

def get_video_info(path):
    cmd = [
        FFPROBE_BIN, "-v", "error", 
        "-select_streams", "v:0", 
        "-show_entries", "stream=width,height,duration", 
        "-of", "json", path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        data = json.loads(result.stdout)
        stream = data['streams'][0]
        return {
            'width': int(stream['width']),
            'height': int(stream['height']),
            'duration': float(stream.get('duration', 0))
        }
    except Exception as e:
        print(f"Error probing video: {e}")
        return None

def detect_black_bars(path, check_time=60):
    print("   [Auto-Detect] Scanning for black bars...")
    cmd = [
        FFMPEG_BIN, "-ss", str(check_time), "-i", path, 
        "-t", "5", "-vf", "cropdetect=24:16:0", "-f", "null", "-"
    ]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", res.stderr)
    
    if matches:
        w, h, x, y = map(int, matches[-1])
        print(f"   [Auto-Detect] Found Active Area: {w}x{h} at x={x}, y={y}")
        return {'w': w, 'h': h, 'x': x, 'y': y}
    else:
        print("   [Auto-Detect] Warning: Could not detect bars. Using full frame.")
        return None

def calculate_smart_crop(src_w, src_h, target_h):
    target_w = int(target_h * (16/9))
    target_w = (target_w // 16) * 16
    
    k = 0
    while True:
        proposed_crop_w = target_w - (32 * k)
        if proposed_crop_w < (target_w / 2): raise ValueError("Cannot find crop width!")
        if proposed_crop_w <= src_w:
            final_crop_w = proposed_crop_w
            break
        k += 1

    padding_per_side = (target_w - final_crop_w) // 2
    crop_x_offset = (src_w - final_crop_w) // 2
    
    return {
        'crop_w': final_crop_w, 'crop_h': target_h,
        'crop_x': crop_x_offset, 'crop_y': 0,
        'final_w': target_w, 'final_h': target_h,
        'pad_width': padding_per_side
    }

def main():
    print(f"--- 1. PREPARE ASSETS (Lossless Intermediate) ---")
    
    chunks_dir = os.path.join(PROJECT_WORKSPACE, "01_Chunks")
    audio_dir = os.path.join(PROJECT_WORKSPACE, "02_Audio")
    if os.path.exists(chunks_dir): shutil.rmtree(chunks_dir)
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    print(f"   Probing: {INPUT_VIDEO}")
    info = get_video_info(INPUT_VIDEO)
    if not info: return

    # 1. DETECT & SHAVE
    active_rect = detect_black_bars(INPUT_VIDEO)
    
    if active_rect:
        calc_w = active_rect['w'] - (SAFETY_SHAVE * 2)
        calc_h = active_rect['h']
        active_rect['x'] += SAFETY_SHAVE
        active_rect['w'] = calc_w 
        print(f"   [Safety Shave] Reduced Width to {calc_w} (Removed {SAFETY_SHAVE}px dirty edges)")
    else:
        calc_w = info['width'] - (SAFETY_SHAVE * 2)
        calc_h = info['height']
        active_rect = {'w': calc_w, 'h': calc_h, 'x': SAFETY_SHAVE, 'y': 0}

    # 2. CALCULATE SPECS
    specs = calculate_smart_crop(calc_w, calc_h, TARGET_HEIGHT)
    
    with open(os.path.join(PROJECT_WORKSPACE, "specs.json"), 'w') as f:
        json.dump(specs, f, indent=4)

    subprocess.run([FFMPEG_BIN, "-y", "-i", INPUT_VIDEO, "-vn", "-c:a", "copy", os.path.join(audio_dir, "master_audio.m4a")], check=True)

    # 3. FILTER CHAIN
    f_depillar = f"crop={active_rect['w']}:{active_rect['h']}:{active_rect['x']}:{active_rect['y']}"
    f_smart = f"crop={specs['crop_w']}:{specs['crop_h']}:{specs['crop_x']}:{specs['crop_y']}"
    f_scale = ""
    if calc_h != specs['final_h']:
        f_scale = f",scale=-1:{specs['final_h']}"

    full_filter = f"{f_depillar},{f_smart}{f_scale}"
    
    segment_pattern = os.path.join(chunks_dir, "chunk_%03d.mp4")
    current_time = 0
    chunk_idx = 0
    
    print("   Splitting Video into Lossless Chunks...")
    while current_time < info['duration']:
        out_name = os.path.join(chunks_dir, f"chunk_{chunk_idx:03d}.mp4")
        
        cmd = [
            FFMPEG_BIN, "-y", 
            "-ss", str(current_time), 
            "-t", str(CHUNK_LENGTH),
            "-i", INPUT_VIDEO, 
            "-vf", full_filter,
            "-r", str(TARGET_FPS), 
            
            # --- THE QUALITY FIX ---
            # crf 0 = Lossless. preset ultrafast = Don't waste CPU compressing it.
            "-c:v", "libx264", "-crf", "0", "-preset", "ultrafast", 
            "-an", 
            out_name
        ]
        
        subprocess.run(cmd, stderr=subprocess.DEVNULL)
        
        if os.path.exists(out_name) and os.path.getsize(out_name) > 0:
            print(f"\r   Processed Chunk {chunk_idx} @ {current_time:.2f}s...", end="")
            chunk_idx += 1
        
        current_time += (CHUNK_LENGTH - OVERLAP)
        if current_time >= info['duration']: break
        
    print("\n   Done.")

if __name__ == "__main__":
    main()


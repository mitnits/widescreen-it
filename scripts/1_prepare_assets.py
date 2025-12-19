import os
import subprocess
import json
import shutil
import sys

# Add parent dir to path so we can import project_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

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

def calculate_smart_crop(src_w, src_h, target_h):
    # 1. Target 16:9 Width (Mod-16)
    target_w = int(target_h * (16/9))
    target_w = (target_w // 16) * 16
    
    # 2. Find optimal Crop Width (Padding must be Mod-16 per side)
    # TotalPadding = TargetW - CropW. TotalPadding must be divisible by 32.
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
    print("--- 1. PREPARE ASSETS ---")
    
    chunks_dir = os.path.join(PROJECT_WORKSPACE, "01_Chunks")
    audio_dir = os.path.join(PROJECT_WORKSPACE, "02_Audio")
    if os.path.exists(chunks_dir): shutil.rmtree(chunks_dir)
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    print(f"   Probing: {INPUT_VIDEO}")
    info = get_video_info(INPUT_VIDEO)
    if not info: return

    specs = calculate_smart_crop(info['width'], info['height'], TARGET_HEIGHT)
    print(f"   Original: {info['width']}x{info['height']}")
    print(f"   Target:   {specs['final_w']}x{specs['final_h']} (Pad: {specs['pad_width']}px)")
    
    # Save Specs
    with open(os.path.join(PROJECT_WORKSPACE, "specs.json"), 'w') as f:
        json.dump(specs, f, indent=4)

    # Extract Audio
    subprocess.run([FFMPEG_BIN, "-y", "-i", INPUT_VIDEO, "-vn", "-c:a", "copy", os.path.join(audio_dir, "master_audio.m4a")], check=True)

    # Split & Crop
    crop_filter = f"crop={specs['crop_w']}:{specs['crop_h']}:{specs['crop_x']}:{specs['crop_y']}"
    if info['height'] != specs['final_h']: crop_filter += f",scale=-1:{specs['final_h']}"

    segment_pattern = os.path.join(chunks_dir, "chunk_%03d.mp4")
    
    # Using Loop for precise overlap control
    current_time = 0
    chunk_idx = 0
    
    print("   Splitting Video...")
    while current_time < info['duration']:
        out_name = os.path.join(chunks_dir, f"chunk_{chunk_idx:03d}.mp4")
        cmd = [
            FFMPEG_BIN, "-y", "-ss", str(current_time), "-t", str(CHUNK_LENGTH),
            "-i", INPUT_VIDEO, "-vf", crop_filter,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-an", out_name
        ]
        subprocess.run(cmd, stderr=subprocess.DEVNULL)
        current_time += (CHUNK_LENGTH - OVERLAP)
        chunk_idx += 1
        print(f"\r   Processed Chunk {chunk_idx}...", end="")
        if current_time >= info['duration']: break
    print("\n   Done.")

if __name__ == "__main__":
    main()


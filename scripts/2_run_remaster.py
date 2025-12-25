import websocket
import uuid
import json
import urllib.request
import os
import glob
import time
import random
import shutil
import sys
import subprocess
import argparse 
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_SERVER = "127.0.0.1:8188"

# WORKFLOW PATHS
WORKFLOW_STD_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api.json")
WORKFLOW_NOREF_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api_no_ref.json")

SPECS_FILE = os.path.join(PROJECT_WORKSPACE, "specs.json")
COMFY_INPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "input")
COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")
LOOPBACK_FILENAME = "current_loopback_ref.png"

# NODE MAP
NODE_MAP = {
    "video_loader":  "71",   
    "image_loader":  "189",  
    "video_saver":   "190",  
    "ref_saver":     "185",  
    "seed_node":     "3",    
    "pad_node":      "110",  
    "frame_count_node": "131", 
    "width_node":    "137",  
    "height_node":   "139"   
}

def get_video_details(file_path):
    cmd = [
        FFPROBE_BIN, "-v", "error", 
        "-select_streams", "v:0", 
        "-show_entries", "stream=nb_frames,duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        file_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = res.stdout.strip().splitlines()
        frames = 0
        dur = 0.0
        for l in lines:
            if l.isdigit(): frames = int(l)
            else: 
                try: dur = float(l)
                except: pass
        if frames == 0 and dur > 0:
            frames = int(dur * 16) 
        return frames, dur
    except:
        return 0, 0.0

def queue_prompt(workflow_json, client_id):
    p = {"prompt": workflow_json, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{COMFY_SERVER}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def setup_environment(specs):
    print("--- Setting up ComfyUI Environment ---")
    chunks = glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4"))
    for c in chunks: shutil.copy(c, COMFY_INPUT_DIR)
    
    if START_METHOD == "BLACK_REF":
        img = Image.new('RGB', (specs['final_w'], specs['final_h']), color=(0, 0, 0))
        img.save(os.path.join(COMFY_INPUT_DIR, LOOPBACK_FILENAME))
        print(f"   [Strategy: BLACK_REF] Created Black Zero-Step Image.")
    else:
        print(f"   [Strategy: NO_REF] Skipping Black Image generation.")

def find_latest_ref(filename_prefix):
    search_path = os.path.join(COMFY_OUTPUT_DIR, f"{filename_prefix}*.png")
    candidates = glob.glob(search_path)
    if not candidates: return None
    return max(candidates, key=os.path.getmtime)

def run_batch(limit_chunks=None, start_chunk=0, forced_seed=None):
    if not os.path.exists(SPECS_FILE): 
        print(f"Error: {SPECS_FILE} not found.")
        return
    with open(SPECS_FILE, 'r') as f: specs = json.load(f)
    
    setup_environment(specs)
    
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    try:
        ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={client_id}")
    except Exception as e:
        print(f"Error connecting to ComfyUI: {e}")
        return

    with open(WORKFLOW_STD_FILE, 'r') as f: workflow_std = json.load(f)
    if START_METHOD == "NO_REF":
        with open(WORKFLOW_NOREF_FILE, 'r') as f: workflow_noref = json.load(f)

    all_chunks = sorted(glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4")))
    
    # --- RESUME LOGIC ---
    if start_chunk > 0:
        print(f"\n[RESUME MODE] Jumping to Chunk {start_chunk}")
        prev_idx = start_chunk - 1
        prev_ref_prefix = f"ref_frame_{prev_idx:03d}"
        prev_ref_img = find_latest_ref(prev_ref_prefix)
        
        if prev_ref_img and os.path.exists(prev_ref_img):
            shutil.copy(prev_ref_img, os.path.join(COMFY_INPUT_DIR, LOOPBACK_FILENAME))
            print(f"   [Resume] Loaded continuity reference: {os.path.basename(prev_ref_img)}")
        else:
            print(f"   [WARNING] No reference found for Chunk {prev_idx}! Starting blind.")

    chunks_to_process = all_chunks[start_chunk:]
    if limit_chunks and limit_chunks > 0:
        chunks_to_process = chunks_to_process[:limit_chunks]
    
    for i, chunk_path in enumerate(chunks_to_process, start=start_chunk):
        fname = os.path.basename(chunk_path)
        frames, dur = get_video_details(chunk_path)
        if dur > 0: fps = frames / dur
        else: fps = 16 
        fps = round(fps)
        
        # --- CLEANUP ---
        prefix_vid = f"remastered_{i:03d}"
        prefix_ref = f"ref_frame_{i:03d}"
        old_files = glob.glob(os.path.join(COMFY_OUTPUT_DIR, f"{prefix_vid}*.mp4")) + \
                    glob.glob(os.path.join(COMFY_OUTPUT_DIR, f"{prefix_ref}*.png"))
        if old_files:
            for f in old_files:
                try: os.remove(f)
                except OSError: pass

        # --- SEED GENERATION ---
        # If user passed --seed, use it. Otherwise, generate random.
        if forced_seed is not None:
            current_seed = forced_seed
            seed_msg = f"Fixed: {current_seed}"
        else:
            current_seed = random.randint(1, 10**10)
            seed_msg = f"Random: {current_seed}"

        # --- STRATEGY SELECTION ---
        if i == 0 and START_METHOD == "NO_REF":
            print(f"\n--- Chunk {i+1} [MODE: NO_REF] [Seed: {seed_msg}]: {fname} ---")
            workflow = workflow_noref.copy()
        else:
            print(f"\n--- Chunk {i+1} [MODE: LOOP] [Seed: {seed_msg}]: {fname} ---")
            workflow = workflow_std.copy()
            workflow[NODE_MAP["image_loader"]]["inputs"]["image"] = LOOPBACK_FILENAME

        # --- INJECTIONS ---
        workflow[NODE_MAP["seed_node"]]["inputs"]["seed"] = current_seed

        pad = int(specs['pad_width'])
        workflow[NODE_MAP["pad_node"]]["inputs"]["left"] = pad
        workflow[NODE_MAP["pad_node"]]["inputs"]["right"] = pad
        workflow[NODE_MAP["pad_node"]]["inputs"]["method"] = "reflect"
        workflow[NODE_MAP["pad_node"]]["inputs"]["feathering"] = 10
        
        workflow[NODE_MAP["width_node"]]["inputs"]["value"] = int(specs['final_w'])
        workflow[NODE_MAP["height_node"]]["inputs"]["value"] = int(specs['final_h'])
        
        workflow[NODE_MAP["frame_count_node"]]["inputs"]["value"] = frames
        workflow[NODE_MAP["video_saver"]]["inputs"]["frame_rate"] = fps * 2

        workflow[NODE_MAP["video_loader"]]["inputs"]["file"] = fname
        
        workflow[NODE_MAP["video_saver"]]["inputs"]["filename_prefix"] = prefix_vid
        if "ref_saver" in NODE_MAP and NODE_MAP["ref_saver"] in workflow:
            workflow[NODE_MAP["ref_saver"]]["inputs"]["filename_prefix"] = prefix_ref

        # --- EXECUTE ---
        prompt_id = queue_prompt(workflow, client_id)['prompt_id']
        while True:
            out = ws.recv()
            if isinstance(out, str):
                msg = json.loads(out)
                if msg['type'] == 'executing' and msg['data']['node'] is None and msg['data']['prompt_id'] == prompt_id:
                    print("   Generation Complete.")
                    break
        
        # --- LOOPBACK CAPTURE ---
        generated_ref = find_latest_ref(prefix_ref)
        if generated_ref and os.path.exists(generated_ref):
            shutil.copy(generated_ref, os.path.join(COMFY_INPUT_DIR, LOOPBACK_FILENAME))
            print(f"   [Loopback] Updated Reference.")
        
        time.sleep(0.5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ComfyUI Remaster Batch")
    parser.add_argument("--chunks", type=int, default=None, help="Limit number of chunks (Debug)")
    parser.add_argument("--start_chunk", type=int, default=0, help="Start from specific chunk index")
    parser.add_argument("--seed", type=int, default=None, help="Force a specific seed for all chunks")
    args = parser.parse_args()
    
    run_batch(limit_chunks=args.chunks, start_chunk=args.start_chunk, forced_seed=args.seed)


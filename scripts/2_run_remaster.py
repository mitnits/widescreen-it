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
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_SERVER = "127.0.0.1:8188"

# --- WORKFLOW CONFIGURATION ---
# 1. Start Workflow: For Chunk 0 (No Reference Image)
WORKFLOW_START_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api_no_ref.json")

# 2. Loop Workflow: For Chunk 1+ (Standard workflow with Reference Input)
WORKFLOW_LOOP_FILE  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api.json")

SPECS_FILE = os.path.join(PROJECT_WORKSPACE, "specs.json")
COMFY_INPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "input")
COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")
LOOPBACK_FILENAME = "current_loopback_ref.png"

# NODE MAP (Must match IDs in BOTH JSONs)
NODE_MAP = {
    "video_loader":  "71",   
    "image_loader":  "189",  # Only exists/active in LOOP workflow
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

def find_latest_ref(filename_prefix):
    search_path = os.path.join(COMFY_OUTPUT_DIR, f"{filename_prefix}*.png")
    candidates = glob.glob(search_path)
    if not candidates: return None
    return max(candidates, key=os.path.getmtime)

def run_batch():
    if not os.path.exists(SPECS_FILE): return
    with open(SPECS_FILE, 'r') as f: specs = json.load(f)
    
    setup_environment(specs)
    
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={client_id}")

    # Load BOTH templates
    with open(WORKFLOW_START_FILE, 'r') as f: workflow_start_tmpl = json.load(f)
    with open(WORKFLOW_LOOP_FILE, 'r') as f:  workflow_loop_tmpl = json.load(f)

    chunks = sorted(glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4")))
    
    for i, chunk_path in enumerate(chunks):
        fname = os.path.basename(chunk_path)
        
        frames, dur = get_video_details(chunk_path)
        if dur > 0: fps = frames / dur
        else: fps = 16 
        fps = round(fps)
        
        # --- SELECT WORKFLOW ---
        if i == 0:
            print(f"\n--- Chunk {i+1} [START MODE - No Ref]: {fname} ---")
            workflow = workflow_start_tmpl.copy() 
        else:
            print(f"\n--- Chunk {i+1} [LOOP MODE - With Ref]: {fname} ---")
            workflow = workflow_loop_tmpl.copy()
            
            # Point to loopback image (Only needed for Loop Mode)
            workflow[NODE_MAP["image_loader"]]["inputs"]["image"] = LOOPBACK_FILENAME

        # --- COMMON INJECTIONS (Apply to BOTH) ---
        
        # 1. Dimensions & Padding (Reflect + Feather)
        pad = int(specs['pad_width'])
        workflow[NODE_MAP["pad_node"]]["inputs"]["left"] = pad
        workflow[NODE_MAP["pad_node"]]["inputs"]["right"] = pad
        workflow[NODE_MAP["pad_node"]]["inputs"]["method"] = "reflect"
        workflow[NODE_MAP["pad_node"]]["inputs"]["feathering"] = 50
        
        workflow[NODE_MAP["width_node"]]["inputs"]["value"] = int(specs['final_w'])
        workflow[NODE_MAP["height_node"]]["inputs"]["value"] = int(specs['final_h'])

        # 2. Timing
        workflow[NODE_MAP["frame_count_node"]]["inputs"]["value"] = frames
        workflow[NODE_MAP["video_saver"]]["inputs"]["frame_rate"] = fps * 2

        # 3. Standard Inputs
        workflow[NODE_MAP["video_loader"]]["inputs"]["file"] = fname
        workflow[NODE_MAP["seed_node"]]["inputs"]["seed"] = random.randint(1, 10**10)
        
        ref_prefix = f"ref_frame_{i:03d}"
        workflow[NODE_MAP["video_saver"]]["inputs"]["filename_prefix"] = f"remastered_{i:03d}"
        
        if "ref_saver" in NODE_MAP and NODE_MAP["ref_saver"] in workflow:
            workflow[NODE_MAP["ref_saver"]]["inputs"]["filename_prefix"] = ref_prefix

        # --- EXECUTE ---
        prompt_id = queue_prompt(workflow, client_id)['prompt_id']
        while True:
            out = ws.recv()
            if isinstance(out, str):
                msg = json.loads(out)
                if msg['type'] == 'executing' and msg['data']['node'] is None and msg['data']['prompt_id'] == prompt_id:
                    print("   Generation Complete.")
                    break
        
        # --- CAPTURE LOOPBACK ---
        generated_ref = find_latest_ref(ref_prefix)
        if generated_ref and os.path.exists(generated_ref):
            shutil.copy(generated_ref, os.path.join(COMFY_INPUT_DIR, LOOPBACK_FILENAME))
            print(f"   [Loopback] Saved {ref_prefix} -> {LOOPBACK_FILENAME}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    run_batch()

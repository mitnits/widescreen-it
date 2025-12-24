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

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_SERVER = "127.0.0.1:8188"
# NOTE: Updated filename to the new no-ref version
WORKFLOW_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api_no_ref.json")
SPECS_FILE = os.path.join(PROJECT_WORKSPACE, "specs.json")
COMFY_OUTPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "output")

# =================================================================
# NODE MAP (Simplified - No Image Loader)
# =================================================================
NODE_MAP = {
    "video_loader":  "71",   
    "video_saver":   "190",  
    "seed_node":     "3",    
    "pad_node":      "110",
    
    # Dimensions
    "frame_count_node": "131", 
    "mask_len_node": "131", 
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

def run_batch():
    if not os.path.exists(SPECS_FILE): return
    with open(SPECS_FILE, 'r') as f: specs = json.load(f)
    
    # Copy chunks to Input (One time setup)
    print("--- Setting up ComfyUI Environment ---")
    chunks = glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4"))
    for c in chunks: 
        shutil.copy(c, os.path.join(COMFYUI_ROOT_DIR, "input"))
    
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={client_id}")

    with open(WORKFLOW_TEMPLATE, 'r') as f: workflow = json.load(f)

    # 1. APPLY PADDING LOGIC (Reflect + Feather)
    pad = int(specs['pad_width'])
    
    workflow[NODE_MAP["pad_node"]]["inputs"]["left"] = pad
    workflow[NODE_MAP["pad_node"]]["inputs"]["right"] = pad
    workflow[NODE_MAP["pad_node"]]["inputs"]["method"] = "reflect" # Fills bars with mirrored video
    workflow[NODE_MAP["pad_node"]]["inputs"]["feathering"] = 50    # Softens the edge
    
    workflow[NODE_MAP["width_node"]]["inputs"]["value"] = int(specs['final_w'])
    workflow[NODE_MAP["height_node"]]["inputs"]["value"] = int(specs['final_h'])

    chunks = sorted(glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4")))
    
    for i, chunk_path in enumerate(chunks):
        fname = os.path.basename(chunk_path)
        
        frames, dur = get_video_details(chunk_path)
        if dur > 0: fps = frames / dur
        else: fps = 16 
        fps = round(fps)
        
        print(f"\n--- Chunk {i+1}: {fname} [{frames} frames @ {fps} fps] ---")

        # Sync Frames & Saver FPS
        workflow[NODE_MAP["frame_count_node"]]["inputs"]["value"] = frames
        workflow[NODE_MAP["video_saver"]]["inputs"]["frame_rate"] = fps * 2

        workflow[NODE_MAP["video_loader"]]["inputs"]["file"] = fname
        workflow[NODE_MAP["seed_node"]]["inputs"]["seed"] = random.randint(1, 10**10)
        
        workflow[NODE_MAP["video_saver"]]["inputs"]["filename_prefix"] = f"remastered_{i:03d}"

        # Execute
        prompt_id = queue_prompt(workflow, client_id)['prompt_id']
        while True:
            out = ws.recv()
            if isinstance(out, str):
                msg = json.loads(out)
                if msg['type'] == 'executing' and msg['data']['node'] is None and msg['data']['prompt_id'] == prompt_id:
                    print("   Generation Complete.")
                    break
        
        time.sleep(0.5)

if __name__ == "__main__":
    run_batch()

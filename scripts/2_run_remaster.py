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
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project_config import *

COMFY_SERVER = "127.0.0.1:8188"
WORKFLOW_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows", "workflow_api.json")
SPECS_FILE = os.path.join(PROJECT_WORKSPACE, "specs.json")
COMFY_INPUT_DIR = os.path.join(COMFYUI_ROOT_DIR, "input")

# --- UPDATE YOUR NODE IDS HERE ---
NODE_MAP = {
    "video_loader":  "71",   # Load Video
    "image_loader":  "189",  # Load Image (Reference)
    "video_saver":   "190",  # VHS_VideoCombine
    "ref_saver":     "185",  # Save Image (Last Frame)
    "seed_node":     "3",    # KSampler
    
    # Dimensions
    "pad_node":      "110",  # ImagePadForOutpaint
    "mask_len_node": "131",  # PrimitiveInt (Mask Size)
    "width_node":    "137",  # PrimitiveInt (Width)
    "height_node":   "139"   # PrimitiveInt (Height)
}

def queue_prompt(workflow_json, client_id):
    p = {"prompt": workflow_json, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{COMFY_SERVER}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_history(prompt_id):
    with urllib.request.urlopen(f"http://{COMFY_SERVER}/history/{prompt_id}") as response:
        return json.loads(response.read())

def setup_environment(specs):
    print("--- Setting up ComfyUI Environment ---")
    ref_name = "zero_step_ref.png"
    img = Image.new('RGB', (specs['final_w'], specs['final_h']), color=(0, 0, 0))
    img.save(os.path.join(COMFY_INPUT_DIR, ref_name))
    
    chunks = glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4"))
    print(f"   Copying {len(chunks)} chunks to {COMFY_INPUT_DIR}...")
    for c in chunks:
        shutil.copy(c, COMFY_INPUT_DIR)
    return ref_name

def run_batch():
    if not os.path.exists(SPECS_FILE): return
    with open(SPECS_FILE, 'r') as f: specs = json.load(f)
    
    zero_ref = setup_environment(specs)
    
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFY_SERVER}/ws?clientId={client_id}")

    with open(WORKFLOW_TEMPLATE, 'r') as f: workflow = json.load(f)

    # Inject Specs
    pad = int(specs['pad_width'])
    workflow[NODE_MAP["pad_node"]]["inputs"]["left"] = pad
    workflow[NODE_MAP["pad_node"]]["inputs"]["right"] = pad
    workflow[NODE_MAP["mask_len_node"]]["inputs"]["value"] = pad
    workflow[NODE_MAP["width_node"]]["inputs"]["value"] = int(specs['final_w'])
    workflow[NODE_MAP["height_node"]]["inputs"]["value"] = int(specs['final_h'])

    chunks = sorted(glob.glob(os.path.join(PROJECT_WORKSPACE, "01_Chunks", "*.mp4")))
    prev_ref = zero_ref
    
    for i, chunk_path in enumerate(chunks):
        fname = os.path.basename(chunk_path)
        print(f"\n--- Chunk {i+1}/{len(chunks)}: {fname} ---")
        
        workflow[NODE_MAP["video_loader"]]["inputs"]["file"] = fname
        workflow[NODE_MAP["image_loader"]]["inputs"]["image"] = prev_ref
        
        workflow[NODE_MAP["seed_node"]]["inputs"]["seed"] = random.randint(1, 10**10)
        workflow[NODE_MAP["video_saver"]]["inputs"]["filename_prefix"] = f"remastered_{i:03d}"
        workflow[NODE_MAP["ref_saver"]]["inputs"]["filename_prefix"] = f"ref_frame_{i:03d}"

        prompt_id = queue_prompt(workflow, client_id)['prompt_id']
        
        while True:
            out = ws.recv()
            if isinstance(out, str):
                msg = json.loads(out)
                if msg['type'] == 'executing' and msg['data']['node'] is None and msg['data']['prompt_id'] == prompt_id:
                    break
        
        try:
            hist = get_history(prompt_id)
            prev_ref = hist[prompt_id]['outputs'][NODE_MAP['ref_saver']]['images'][0]['filename']
        except:
            prev_ref = zero_ref
        
        time.sleep(0.5)

if __name__ == "__main__":
    run_batch()


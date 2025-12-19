# Widescreen-It: Infinite Outpainting Driver

A Python driver for ComfyUI + Wan 2.1 to remaster 4:3 videos into 16:9 widescreen with perfect consistency.

## Setup
1. Edit `project_config.py` with your input video path and ComfyUI folder.
2. Ensure you have the ComfyUI workflow loaded or use the JSON in `workflows/`.
3. Install requirements: `pip install -r requirements.txt`

## Usage
1. **Prepare Assets:** `python scripts/1_prepare_assets.py`
   (Calculates crop and splits video)
2. **Run AI:** `python scripts/2_run_remaster.py`
   (Injects chunks into ComfyUI loopback)
3. **Stitch:** `python scripts/3_stitch_pro_sync.py`
   (Merges and syncs to audio)

import os
import sys

# USER CONFIGURATION

# 1. PATHS
# Use r strings for Windows paths
INPUT_VIDEO = r"D:\Inputs\Guns_N_Roses_-_November_Rain_720p.mp4"
PROJECT_WORKSPACE = r"D:\Projects\november_rain"
COMFYUI_ROOT_DIR = r"D:\CU"

# 2. OUTPUT SETTINGS
TARGET_HEIGHT = 720 

# 3. CHUNK SETTINGS
CHUNK_LENGTH = 9.8 
OVERLAP = 1.0

# 4. EXECUTABLES
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

# 5. STARTUP STRATEGY
# "BLACK_REF" = Create a black image and use standard workflow (Best for fade-ins)
# "NO_REF"    = Use 'workflow_api_no_ref.json' for Chunk 0 (Best for instant starts)
START_METHOD = "BLACK_REF"


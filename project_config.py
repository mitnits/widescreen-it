import os
import sys

# ==========================================
#           USER CONFIGURATION
# ==========================================

# 1. PATHS (Windows Style for Python compatibility)
# We use r"..." strings to handle backslashes correctly

# The Input Video Source
INPUT_VIDEO = r"D:\Inputs\Old_Man_River.mp4"

# Where the project artifacts (chunks, audio, output) will live
# This keeps your repo clean; artifacts go to a separate workspace.
PROJECT_WORKSPACE = r"D:\Projects\old_man_river"

# ComfyUI Installation (For auto-copying chunks to 'input')
COMFYUI_ROOT_DIR = r"D:\CU"

# 2. OUTPUT SETTINGS
TARGET_HEIGHT = 720 

# 3. CHUNK SETTINGS
# 9.8s is the "Golden Number" for Wan 2.1 Context
CHUNK_LENGTH = 9.8 
OVERLAP = 1.0

# 4. EXECUTABLES
# If these are in your global PATH, just use the command name.
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

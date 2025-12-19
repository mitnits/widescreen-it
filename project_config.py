import os
import sys

# USER CONFIGURATION

# 1. PATHS
# Use r strings for Windows paths
INPUT_VIDEO = r"D:\Inputs\Old_Man_River.mp4"
PROJECT_WORKSPACE = r"D:\Projects\old_man_river"
COMFYUI_ROOT_DIR = r"D:\CU"

# 2. OUTPUT SETTINGS
TARGET_HEIGHT = 720 

# 3. CHUNK SETTINGS
CHUNK_LENGTH = 9.8 
OVERLAP = 1.0

# 4. EXECUTABLES
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

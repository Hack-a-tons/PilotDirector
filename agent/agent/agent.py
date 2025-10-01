from typing import Annotated, List, Optional, Any
import os
import subprocess
import json
from dotenv import load_dotenv
from contextvars import ContextVar

from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool
from llama_index.protocols.ag_ui.router import get_ag_ui_workflow_router

# Load environment variables early to support local development via .env
load_dotenv()

# Context variable to store current user_id
current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)

def run_external_command(cmd: List[str], description: str = "") -> subprocess.CompletedProcess:
    """Run external command with minimal logging."""
    # Add -v quiet to ffmpeg/ffprobe commands to reduce verbosity, except for scene detection
    if cmd[0] in ['ffmpeg', 'ffprobe'] and '-v' not in cmd and 'showinfo' not in ' '.join(cmd):
        cmd = cmd[:1] + ['-v', 'quiet'] + cmd[1:]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Command failed: {' '.join(cmd[:3])}... (exit code: {result.returncode})")
    return result

# Video processing tools
def get_video_info(filename: str, user_id: str = None) -> str:
    """Get information about a video file using ffprobe."""
    try:
        video_path = find_user_file(filename, user_id)
        if not video_path:
            return f"Error: Video file {filename} not found"
        
        # Use cached helper function
        info = get_video_info_helper(video_path, filename)
        
        # Get file stats for modification time
        stat = os.stat(video_path)
        from datetime import datetime
        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        return f"Video info for {filename}: Duration: {info['duration']:.2f}s, Size: {info['size']} bytes ({info['size']/1024/1024:.1f} MB), Resolution: {info['width']}x{info['height']}, Modified: {mod_time}"
    except Exception as e:
        return f"Error getting video info for {filename}: {str(e)}"

def generate_unique_filename(base_path: str, filename: str) -> str:
    """Generate a unique filename by adding a number suffix if file exists."""
    full_path = os.path.join(base_path, filename)
    if not os.path.exists(full_path):
        return filename
    
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        new_path = os.path.join(base_path, new_filename)
        if not os.path.exists(new_path):
            return new_filename
        counter += 1

def cut_video(filename: str, start_time: str, duration: str, output_filename: str, user_id: str = None) -> str:
    """Cut a video segment using ffmpeg."""
    try:
        print(f"[DEBUG] cut_video called with user_id: {user_id}, filename: {filename}")
        
        input_path = find_user_file(filename, user_id)
        if not input_path:
            return f"Error: Input video {filename} not found"
        
        # Use the directory of the input file as output directory
        output_dir = os.path.dirname(input_path)
        print(f"[DEBUG] cut_video output_dir: {output_dir}")
        
        # Generate unique output filename in the same directory as input file
        unique_output = generate_unique_filename(output_dir, output_filename)
        output_path = os.path.join(output_dir, unique_output)
        print(f"[DEBUG] cut_video output_path: {output_path}")
        
        # Get video duration first to validate
        info_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", input_path]
        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        
        if info_result.returncode == 0:
            video_duration = float(info_result.stdout.strip())
            start_seconds = float(start_time)
            duration_seconds = float(duration)
            
            if start_seconds >= video_duration:
                return f"Error: Start time {start_time}s is beyond video duration ({video_duration:.2f}s)"
            
            if start_seconds + duration_seconds > video_duration:
                return f"Warning: Requested duration extends beyond video end. Cutting from {start_time}s to end of video ({video_duration:.2f}s)"
        
        # Put -ss before -i for better seeking performance
        cmd = [
            "ffmpeg", "-ss", start_time, "-i", input_path, 
            "-t", duration, "-c:v", "libx264", "-c:a", "aac", output_path, "-y"
        ]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error cutting video: {result.stderr}"
        
        # Verify output file was created and has reasonable size
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            if size < 1000:  # Less than 1KB is suspicious
                print(f"[DEV] Warning: Small output file {unique_output} ({size} bytes)")
                return f"Warning: Output file {unique_output} created but very small ({size} bytes). Check if cut parameters are correct."
        
        return f"Successfully cut {filename} from {start_time}s for {duration}s, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in cut_video: {str(e)}")
        return f"Error cutting video {filename}: {str(e)}"

def concatenate_videos(filenames: List[str], output_filename: str, preserve_order: bool = False, user_id: str = None) -> str:
    """Concatenate multiple videos using ffmpeg."""
    try:
        print(f"[DEBUG] concatenate_videos called with user_id: {user_id}")
        print(f"[DEBUG] filenames: {filenames}")
        print(f"[DEBUG] output_filename: {output_filename}")
        
        # Only sort alphabetically if order is not explicitly specified by user
        if preserve_order:
            sorted_filenames = filenames  # Keep user-specified order
        else:
            sorted_filenames = sorted(filenames)  # Sort alphabetically for "all videos"
        
        # Find the first input file to determine the user directory
        first_file_path = find_user_file(sorted_filenames[0], user_id)
        if not first_file_path:
            return f"Error: Video file {sorted_filenames[0]} not found"
        
        # Use the directory of the first input file as output directory
        output_dir = os.path.dirname(first_file_path)
        print(f"[DEBUG] output_dir from first file: {output_dir}")
        
        file_list_path = os.path.join(output_dir, "temp_filelist.txt")
        
        with open(file_list_path, "w") as f:
            for filename in sorted_filenames:
                file_path = find_user_file(filename, user_id)
                if file_path:
                    # Use relative path for ffmpeg
                    rel_path = os.path.relpath(file_path, output_dir)
                    f.write(f"file '{rel_path}'\n")
        
        # Generate unique output filename in the same directory as input files
        unique_output = generate_unique_filename(output_dir, output_filename)
        output_path = os.path.join(output_dir, unique_output)
        print(f"[DEBUG] output_path: {output_path}")
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", 
            "-i", file_list_path, "-c", "copy", output_path, "-y"
        ]
        
        print(f"[DEBUG] FFmpeg command: {' '.join(cmd)}")
        print(f"[DEBUG] Working directory: {os.getcwd()}")
        print(f"[DEBUG] Output directory: {output_dir}")
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, f"Concatenate videos to {output_filename}")
        
        # Clean up temp file
        if os.path.exists(file_list_path):
            os.remove(file_list_path)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error concatenating videos: {result.stderr}"
        
        return f"Successfully concatenated {len(filenames)} videos into {unique_output}. Please refresh the file list."
    except Exception as e:
        return f"Error: {str(e)}"

def get_current_user_dir():
    """Get the current user's video directory. If no user_id, find the directory with files."""
    user_id = current_user_id.get()
    
    if user_id and user_id != 'None':
        return get_current_user_dir()
    
    # Fallback: find directory with video files
    base_dir = "../videos"
    try:
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                # Check if this directory has video files
                files = os.listdir(item_path)
                if any(f.endswith(('.mp4', '.avi', '.mov')) for f in files):
                    print(f"[DEBUG] Using directory with files: {item_path}")
                    return item_path
    except:
        pass
    
    return base_dir

def find_user_file(filename: str, user_id: str = None) -> str:
    """Find a file in the current user's directory."""
    if os.path.exists(filename):
        return filename
    
    user_dir = get_current_user_dir()
    file_path = os.path.join(user_dir, filename)
    
    if os.path.exists(file_path):
        return file_path
    
    print(f"[DEBUG] File '{filename}' not found in {user_dir}")
    return None

def extract_frame(filename: str, timestamp: str, output_filename: str, user_id: str = None) -> str:
    """Extract a frame from a video at a specific timestamp."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input video {filename} not found"
        
        # Generate unique output filename in user directory
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        # Handle "last" frame request
        if timestamp.lower() in ['last', 'end', 'final']:
            # Use FFmpeg to extract the last frame without needing duration
            cmd = [
                "ffmpeg", "-sseof", "-1", "-i", input_path, 
                "-vframes", "1", output_path, "-y"
            ]
        else:
            # Get video duration first to validate timestamp for specific times
            info_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", input_path]
            info_result = subprocess.run(info_cmd, capture_output=True, text=True)
            
            if info_result.returncode == 0:
                video_duration = float(info_result.stdout.strip())
                timestamp_seconds = float(timestamp)
                
                if timestamp_seconds >= video_duration:
                    return f"Error: Timestamp {timestamp}s is beyond video duration ({video_duration:.2f}s). Video is only {video_duration:.2f} seconds long."
            
            cmd = [
                "ffmpeg", "-i", input_path, "-ss", timestamp, 
                "-vframes", "1", output_path, "-y"
            ]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error extracting frame: {result.stderr}"
        
        return f"Successfully extracted frame from {filename} at {timestamp}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in extract_frame: {str(e)}")
        return f"Error extracting frame from {filename}: {str(e)}"

# Cache for video info to prevent repeated ffprobe calls
_video_info_cache = {}

def get_video_info_helper(file_path: str, filename: str) -> dict:
    """Helper function to get video info using ffprobe."""
    # Simple cache based on file path only
    if file_path in _video_info_cache:
        print(f"[DEBUG] Using cached info for {filename}")
        return _video_info_cache[file_path]
    
    print(f"[DEBUG] Making NEW ffprobe call for {filename}")
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]
        result = run_external_command(cmd, f"Get video info for {filename}")
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            format_info = data.get("format", {})
            video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
            
            duration = float(format_info.get("duration", 0))
            size = int(format_info.get("size", 0))
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            
            # Get FPS and calculate frame count
            fps = 30.0  # Default
            if video_stream.get("r_frame_rate"):
                try:
                    fps_str = video_stream["r_frame_rate"]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        fps = float(num) / float(den)
                    else:
                        fps = float(fps_str)
                except:
                    fps = 30.0
            
            frame_count = int(duration * fps)
            
            video_info = {
                "filename": filename,
                "duration": duration,
                "size": size,
                "width": width,
                "height": height,
                "fps": fps,
                "frame_count": frame_count
            }
            
            # Cache the result
            _video_info_cache[file_path] = video_info
            return video_info
    except Exception as e:
        print(f"[DEV] Error getting info for {filename}: {e}")
    
    return {
        "filename": filename,
        "duration": 0,
        "size": 0,
        "width": 0,
        "height": 0,
        "fps": 30.0,
        "frame_count": 0
    }

def list_videos(user_id: str = None) -> str:
    """List all video files in user directory with basic info."""
    try:
        print(f"[DEV] list_videos() called - starting execution")
        
        # Use current user directory only
        user_dir = get_current_user_dir()
        print(f"[DEBUG] Using user directory: {user_dir}")
        
        if not os.path.exists(user_dir):
            print(f"[DEV] User directory not found: {user_dir}")
            return "User directory not found"
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                           '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                           '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                           '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf']
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                           '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                           '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f']
        
        videos = []
        images = []
        
        # Check only the current user directory
        try:
            user_files = os.listdir(user_dir)
            print(f"[DEBUG] Files in user directory: {user_files}")
            for file in user_files:
                file_path = os.path.join(user_dir, file)
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    print(f"[DEV] Processing video file: {file}")
                    video_info = get_video_info_helper(file_path, file)
                    videos.append(video_info)
                elif any(file.lower().endswith(ext) for ext in image_extensions):
                    images.append({"filename": file, "type": "image"})
        except Exception as e:
            print(f"[DEV] Error reading user directory {user_dir}: {e}")
            return f"Error reading user directory: {e}"
        
        print(f"[DEV] Returning info for {len(videos)} videos and {len(images)} images")
        
        if not videos and not images:
            return "No video or image files found in your directory."
        
        result = []
        
        if videos:
            result.append("You have the following video files:\n")
            for video in videos:
                duration = video.get('duration', 0)
                size = video.get('size', 0)
                width = video.get('width', 0)
                height = video.get('height', 0)
                fps = video.get('fps', 0)
                frame_count = video.get('frame_count', 0)
                
                size_mb = size / (1024 * 1024) if size > 0 else 0
                result.append(f"{video['filename']}: {duration:.1f}s ({frame_count} frames @{fps:.1f}fps), {size_mb:.1f}MB, {width}x{height}")
        
        if images:
            result.append(f"\nYou also have {len(images)} image files.")
        
        result.append("\nLet me know if you want to perform any actions on these files.")
        
        return "\n".join(result)
    
    except Exception as e:
        return f"Error listing videos: {str(e)}"

def resize_media(filename: str, output_filename: str, width: int = 0, height: int = 0, scale: str = "", user_id: str = None) -> str:
    """Resize video or image. Use width/height for exact size, or scale for proportional (e.g. '0.5' for 50%)."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        if scale:
            # Proportional scaling
            filter_str = f"scale=iw*{scale}:ih*{scale}"
        elif width > 0 and height > 0:
            # Exact dimensions
            filter_str = f"scale={width}:{height}"
        elif width > 0:
            # Width only, maintain aspect ratio
            filter_str = f"scale={width}:-1"
        elif height > 0:
            # Height only, maintain aspect ratio
            filter_str = f"scale=-1:{height}"
        else:
            return "Error: Must specify width, height, or scale parameter"
        
        cmd = ["ffmpeg", "-i", input_path, "-vf", filter_str, output_path, "-y"]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error resizing: {result.stderr}"
        
        return f"Successfully resized {filename}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in resize_media: {str(e)}")
        return f"Error resizing {filename}: {str(e)}"

def change_aspect_ratio(filename: str, output_filename: str, ratio: str, method: str = "pad", user_id: str = None) -> str:
    """Change aspect ratio of video/image. Ratio like '16:9', '4:3', '1:1'. Method: 'pad' (add bars) or 'crop'."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        # Parse aspect ratio
        try:
            w_ratio, h_ratio = map(int, ratio.split(':'))
        except:
            return f"Error: Invalid aspect ratio '{ratio}'. Use format like '16:9' or '4:3'"
        
        if method.lower() == "pad":
            # Add black bars to fit aspect ratio
            filter_str = f"pad=ih*{w_ratio}/{h_ratio}:ih:(ow-iw)/2:(oh-ih)/2"
        elif method.lower() == "crop":
            # Crop to fit aspect ratio
            filter_str = f"crop=ih*{w_ratio}/{h_ratio}:ih"
        else:
            return f"Error: Invalid method '{method}'. Use 'pad' or 'crop'"
        
        cmd = ["ffmpeg", "-i", input_path, "-vf", filter_str, output_path, "-y"]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error changing aspect ratio: {result.stderr}"
        
        return f"Successfully changed aspect ratio of {filename} to {ratio}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in change_aspect_ratio: {str(e)}")
        return f"Error changing aspect ratio of {filename}: {str(e)}"

def rotate_media(filename: str, output_filename: str, angle: int, user_id: str = None) -> str:
    """Rotate video or image by specified angle (90, 180, 270 degrees)."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        # Map angles to transpose values
        if angle == 90:
            filter_str = "transpose=1"
        elif angle == 180:
            filter_str = "transpose=1,transpose=1"
        elif angle == 270:
            filter_str = "transpose=2"
        else:
            return f"Error: Unsupported angle {angle}. Use 90, 180, or 270 degrees"
        
        cmd = ["ffmpeg", "-i", input_path, "-vf", filter_str, output_path, "-y"]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error rotating: {result.stderr}"
        
        return f"Successfully rotated {filename} by {angle} degrees, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in rotate_media: {str(e)}")
        return f"Error rotating {filename}: {str(e)}"

def recode_video(filename: str, output_filename: str, format: str = "mp4", quality: str = "medium", user_id: str = None) -> str:
    """Recode video to different format/quality. Format: mp4, webm, avi. Quality: high, medium, low, 720p, 1080p."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        # Auto-generate output filename if not provided with extension
        if not output_filename.endswith(('.mp4', '.webm', '.avi', '.mov')):
            base_name = os.path.splitext(output_filename)[0]
            output_filename = f"{base_name}.{format}"
        
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        # Build FFmpeg command based on quality/resolution
        cmd = ["ffmpeg", "-i", input_path]
        
        if quality.lower() == "720p":
            cmd.extend(["-vf", "scale=-1:720", "-crf", "23"])
        elif quality.lower() == "1080p":
            cmd.extend(["-vf", "scale=-1:1080", "-crf", "20"])
        elif quality.lower() == "high":
            cmd.extend(["-crf", "18"])  # High quality
        elif quality.lower() == "medium":
            cmd.extend(["-crf", "23"])  # Medium quality (default)
        elif quality.lower() == "low":
            cmd.extend(["-crf", "28"])  # Low quality, smaller file
        else:
            cmd.extend(["-crf", "23"])  # Default to medium
        
        # Add codec settings based on format
        if format.lower() == "mp4":
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
        elif format.lower() == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-c:a", "libopus"])
        elif format.lower() in ["avi", "mov"]:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
        
        # Add output and overwrite flag
        cmd.extend([output_path, "-y"])
        
        print(f"[DEV] Executing FFmpeg recode: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error recoding video: {result.stderr}"
        
        # Get file sizes for comparison
        try:
            original_size = os.path.getsize(input_path) / (1024 * 1024)  # MB
            new_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
            compression = ((original_size - new_size) / original_size) * 100
            
            return f"Successfully recoded {filename} to {unique_output} ({quality} quality). Original: {original_size:.1f}MB → New: {new_size:.1f}MB ({compression:.1f}% smaller). Please refresh the file list."
        except:
            return f"Successfully recoded {filename} to {unique_output} ({quality} quality). Please refresh the file list."
            
    except Exception as e:
        print(f"[DEV] Exception in recode_video: {str(e)}")
        return f"Error recoding {filename}: {str(e)}"

def crop_image(filename: str, output_filename: str, crop_type: str = "auto", user_id: str = None) -> str:
    """Crop an image to remove black bars or borders. crop_type: 'auto', 'top-bottom', 'left-right', or 'manual'."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input image {filename} not found"
        
        # Generate unique output filename
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        if crop_type.lower() in ['auto', 'black', 'letterbox']:
            # Try multiple sensitivity levels for cropdetect
            for threshold in [24, 16, 8, 4]:
                cmd = [
                    "ffmpeg", "-i", input_path, 
                    "-vf", f"cropdetect={threshold}:16:0", 
                    "-f", "null", "-"
                ]
                
                print(f"[DEV] Detecting crop area (threshold {threshold}): {' '.join(cmd)}")
                result = run_external_command(cmd, "External command")
                
                if result.returncode != 0:
                    continue
                
                # Extract crop parameters from output
                crop_lines = [line for line in result.stderr.split('\n') if 'crop=' in line]
                
                if crop_lines:
                    # Get the most common crop suggestion
                    crop_line = crop_lines[-1]  # Use the last (most refined) detection
                    crop_filter = crop_line.split('crop=')[1].split()[0]
                    
                    # Check if crop actually removes something significant
                    crop_params = crop_filter.split(':')
                    if len(crop_params) >= 4:
                        orig_w, orig_h = crop_params[0], crop_params[1]
                        # If crop removes less than 5% of image, try next threshold
                        try:
                            if int(orig_w) > 0 and int(orig_h) > 0:
                                break
                        except:
                            continue
            
            if not crop_lines:
                return f"No significant black bars detected in {filename}. Try 'top-bottom' or 'left-right' for manual cropping."
            
            # Apply the crop
            cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", f"crop={crop_filter}",
                output_path, "-y"
            ]
            
        elif crop_type.lower() == 'top-bottom':
            # Crop top and bottom 10% (common letterbox removal)
            cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", "crop=iw:ih*0.8:0:ih*0.1",
                output_path, "-y"
            ]
            
        elif crop_type.lower() == 'left-right':
            # Crop left and right 10% (common pillarbox removal)
            cmd = [
                "ffmpeg", "-i", input_path,
                "-vf", "crop=iw*0.8:ih:iw*0.1:0",
                output_path, "-y"
            ]
            
        else:
            return f"Error: Unsupported crop type '{crop_type}'. Use 'auto', 'top-bottom', or 'left-right'."
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error cropping image: {result.stderr}"
        
        return f"Successfully cropped {filename} ({crop_type}), saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in crop_image: {str(e)}")
        return f"Error cropping image {filename}: {str(e)}"

def drop_frames(filename: str, position: str, count: int = 1, user_id: str = None) -> str:
    """Drop frames from video. Position: 'first', 'last', 'middle', or frame number (e.g. '25')."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Video file {filename} not found"
        
        # Get video info
        info_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration:stream=r_frame_rate,nb_frames", "-select_streams", "v:0", "-of", "csv=p=0", input_path]
        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        
        if info_result.returncode != 0:
            return f"Error getting video info for {filename}"
        
        lines = info_result.stdout.strip().split('\n')
        duration = float(lines[0]) if lines else 0
        
        # Get FPS
        fps = 30.0  # Default
        if len(lines) > 1:
            try:
                fps_str = lines[1]
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
            except:
                fps = 30.0
        
        total_frames = int(duration * fps)
        frame_duration = 1.0 / fps
        
        print(f"[DEV] Video: {duration:.3f}s, {fps:.2f}fps, {total_frames} frames")
        
        temp_path = input_path + ".temp"
        
        # Determine what to drop based on position
        if position.lower() == 'first':
            # Drop first N frames
            start_time = count * frame_duration
            cmd = [
                "ffmpeg", "-i", input_path, "-ss", str(start_time),
                "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                temp_path, "-y"
            ]
            action = f"first {count} frame(s)"
            
        elif position.lower() == 'last':
            # Drop last N frames
            new_duration = duration - (count * frame_duration)
            cmd = [
                "ffmpeg", "-i", input_path, "-t", str(new_duration),
                "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                temp_path, "-y"
            ]
            action = f"last {count} frame(s)"
            
        elif position.lower() == 'middle':
            # Drop N frames from middle
            middle_frame = total_frames // 2
            start_frame = middle_frame - (count // 2)
            end_frame = start_frame + count
            
            # Create two segments and concatenate
            segment1_end = start_frame * frame_duration
            segment2_start = end_frame * frame_duration
            
            # First segment
            seg1_path = input_path + ".seg1.mp4"
            cmd1 = [
                "ffmpeg", "-i", input_path, "-t", str(segment1_end),
                "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                seg1_path, "-y"
            ]
            
            # Second segment  
            seg2_path = input_path + ".seg2.mp4"
            cmd2 = [
                "ffmpeg", "-i", input_path, "-ss", str(segment2_start),
                "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                seg2_path, "-y"
            ]
            
            # Execute both segments
            result1 = subprocess.run(cmd1, capture_output=True, text=True)
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            
            if result1.returncode == 0 and result2.returncode == 0:
                # Concatenate segments
                filelist_path = input_path + ".filelist.txt"
                with open(filelist_path, "w") as f:
                    f.write(f"file '{seg1_path}'\n")
                    f.write(f"file '{seg2_path}'\n")
                
                cmd = [
                    "ffmpeg", "-f", "concat", "-safe", "0", "-i", filelist_path,
                    "-c", "copy", temp_path, "-y"
                ]
                
                result = run_external_command(cmd, "External command")
                
                # Clean up temp files
                for temp_file in [seg1_path, seg2_path, filelist_path]:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        
                if result.returncode == 0:
                    os.replace(temp_path, input_path)
                    return f"Successfully dropped {count} frame(s) from middle of {filename} (frames {start_frame}-{end_frame})"
                else:
                    return f"Error concatenating segments: {result.stderr}"
            else:
                return f"Error creating segments: {result1.stderr} {result2.stderr}"
                
        elif position.isdigit():
            # Drop specific frame number
            frame_num = int(position)
            if frame_num < 1 or frame_num > total_frames:
                return f"Frame {frame_num} is out of range (1-{total_frames})"
            
            # Create segments before and after the frame
            before_end = (frame_num - 1) * frame_duration
            after_start = (frame_num + count - 1) * frame_duration
            
            if before_end <= 0:
                # Just drop from beginning
                cmd = [
                    "ffmpeg", "-i", input_path, "-ss", str(after_start),
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                    temp_path, "-y"
                ]
                action = f"frame(s) {frame_num}-{frame_num + count - 1}"
            elif after_start >= duration:
                # Just drop from end
                cmd = [
                    "ffmpeg", "-i", input_path, "-t", str(before_end),
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                    temp_path, "-y"
                ]
                action = f"frame(s) {frame_num}-{frame_num + count - 1}"
            else:
                # Drop from middle - same logic as 'middle' but specific position
                seg1_path = input_path + ".seg1.mp4"
                cmd1 = [
                    "ffmpeg", "-i", input_path, "-t", str(before_end),
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                    seg1_path, "-y"
                ]
                
                seg2_path = input_path + ".seg2.mp4"
                cmd2 = [
                    "ffmpeg", "-i", input_path, "-ss", str(after_start),
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
                    seg2_path, "-y"
                ]
                
                result1 = subprocess.run(cmd1, capture_output=True, text=True)
                result2 = subprocess.run(cmd2, capture_output=True, text=True)
                
                if result1.returncode == 0 and result2.returncode == 0:
                    filelist_path = input_path + ".filelist.txt"
                    with open(filelist_path, "w") as f:
                        f.write(f"file '{seg1_path}'\n")
                        f.write(f"file '{seg2_path}'\n")
                    
                    cmd = [
                        "ffmpeg", "-f", "concat", "-safe", "0", "-i", filelist_path,
                        "-c", "copy", temp_path, "-y"
                    ]
                    
                    result = run_external_command(cmd, "External command")
                    
                    for temp_file in [seg1_path, seg2_path, filelist_path]:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            
                    if result.returncode == 0:
                        os.replace(temp_path, input_path)
                        return f"Successfully dropped frame(s) {frame_num}-{frame_num + count - 1} from {filename}"
                    else:
                        return f"Error concatenating segments: {result.stderr}"
                else:
                    return f"Error creating segments: {result1.stderr} {result2.stderr}"
        else:
            return f"Invalid position '{position}'. Use 'first', 'last', 'middle', or frame number."
        
        # Execute simple commands (first/last)
        if 'cmd' in locals():
            print(f"[DEV] Dropping {action} from {filename}: {' '.join(cmd)}")
            result = run_external_command(cmd, "External command")
            
            if result.returncode == 0:
                os.replace(temp_path, input_path)
                return f"Successfully dropped {action} from {filename}"
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return f"Error dropping {action} from {filename}: {result.stderr}"
            
    except Exception as e:
        return f"Error dropping frames from {filename}: {str(e)}"

def drop_first_frame(filename: str, user_id: str = None) -> str:
    """Drop the first frame from a video and save under the same name."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Video file {filename} not found"
        
        # Get FPS to calculate one frame duration
        fps_cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", input_path]
        fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
        
        fps = 30.0  # Default
        if fps_result.returncode == 0 and fps_result.stdout.strip():
            try:
                fps_str = fps_result.stdout.strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
            except:
                fps = 30.0
        
        one_frame_duration = 1.0 / fps
        temp_path = input_path + ".temp"
        
        cmd = [
            "ffmpeg", "-i", input_path, "-ss", str(one_frame_duration),
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
            temp_path, "-y"
        ]
        
        print(f"[DEV] Dropping first frame from {filename}: {' '.join(cmd)}")
        # Don't use run_external_command to avoid -v quiet flag for debugging
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Replace original with modified version
            os.replace(temp_path, input_path)
            return f"Successfully dropped first frame from {filename}"
        else:
            print(f"[ERROR] FFmpeg error: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return f"Error dropping first frame from {filename}: {result.stderr}"
            
    except Exception as e:
        return f"Error dropping first frame from {filename}: {str(e)}"

def drop_last_frame(filename: str, user_id: str = None) -> str:
    """Drop the last frame from a video and save under the same name."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Video file {filename} not found"
        
        # Get video duration and FPS
        duration_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", input_path]
        fps_cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", input_path]
        
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
        
        if duration_result.returncode != 0:
            return f"Error getting video duration for {filename}"
        
        duration = float(duration_result.stdout.strip())
        
        fps = 30.0  # Default
        if fps_result.returncode == 0 and fps_result.stdout.strip():
            try:
                fps_str = fps_result.stdout.strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
            except Exception as e:
                print(f"[DEV] Could not parse FPS '{fps_str}': {e}, using default 30")
                fps = 30.0
        
        one_frame_duration = 1.0 / fps
        new_duration = duration - one_frame_duration
        temp_path = input_path + ".temp.mp4"  # Ensure proper extension
        
        print(f"[DEV] Dropping last frame: duration={duration:.3f}s, fps={fps:.2f}, new_duration={new_duration:.3f}s")
        print(f"[DEV] Input: {input_path}")
        print(f"[DEV] Temp: {temp_path}")
        
        cmd = [
            "ffmpeg", "-i", input_path, "-t", str(new_duration),
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "128k",
            temp_path, "-y"
        ]
        
        print(f"[DEV] Dropping last frame from {filename}: {' '.join(cmd)}")
        result = run_external_command(cmd, "External command")
        
        if result.returncode == 0:
            # Replace original with modified version
            os.replace(temp_path, input_path)
            return f"Successfully dropped last frame from {filename}"
        else:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return f"Error dropping last frame from {filename}: {result.stderr}"
            
    except Exception as e:
        return f"Error dropping last frame from {filename}: {str(e)}"

def trim_empty_frames(filename: str, output_filename: str = None, user_id: str = None) -> str:
    """Detect and remove empty/black frames from the beginning and end of a video."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        if not output_filename:
            base_name = os.path.splitext(filename)[0]
            output_filename = f"{base_name}_trimmed.mp4"
        
        user_videos_dir = get_current_user_dir()
        os.makedirs(user_videos_dir, exist_ok=True)
        unique_output = generate_unique_filename(user_videos_dir, output_filename)
        output_path = os.path.join(user_videos_dir, unique_output)
        
        print(f"[DEV] Detecting empty frames in {filename}")
        
        # Detect black frames at start and end
        # Use blackdetect filter to find black/empty frames
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", "blackdetect=d=0.1:pix_th=0.1",
            "-f", "null", "-"
        ]
        
        result = run_external_command(cmd, "External command")
        
        # Parse blackdetect output to find start and end trim points
        black_periods = []
        for line in result.stderr.split('\n'):
            if 'blackdetect' in line and 'black_start:' in line:
                try:
                    # Extract black_start and black_end times
                    parts = line.split()
                    start_time = None
                    end_time = None
                    
                    for part in parts:
                        if part.startswith('black_start:'):
                            start_time = float(part.split(':')[1])
                        elif part.startswith('black_end:'):
                            end_time = float(part.split(':')[1])
                    
                    if start_time is not None and end_time is not None:
                        black_periods.append((start_time, end_time))
                except:
                    continue
        
        # Get video duration
        duration_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", input_path]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        total_duration = float(duration_result.stdout.strip()) if duration_result.returncode == 0 else 0
        
        # Determine trim points
        trim_start = 0.0
        trim_end = total_duration
        
        # Find black frames at the beginning
        for start, end in black_periods:
            if start <= 0.1:  # Black frames at the very beginning
                trim_start = max(trim_start, end)
        
        # Find black frames at the end
        for start, end in black_periods:
            if end >= total_duration - 0.1:  # Black frames at the very end
                trim_end = min(trim_end, start)
        
        # Only trim if we found empty frames
        if trim_start > 0 or trim_end < total_duration:
            print(f"[DEV] Trimming empty frames: start={trim_start:.3f}s, end={trim_end:.3f}s")
            
            # Build trim command
            cmd = ["ffmpeg", "-i", input_path]
            
            if trim_start > 0:
                cmd.extend(["-ss", str(trim_start)])
            
            if trim_end < total_duration:
                duration = trim_end - trim_start
                cmd.extend(["-t", str(duration)])
            
            cmd.extend([
                "-c:v", "libx264", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                output_path, "-y"
            ])
            
            print(f"[DEV] Trimming command: {' '.join(cmd)}")
            result = run_external_command(cmd, "External command")
            
            if result.returncode == 0:
                return f"Successfully trimmed empty frames from {filename} → {unique_output}. Removed {trim_start:.3f}s from start and {total_duration - trim_end:.3f}s from end."
            else:
                return f"Error trimming {filename}: {result.stderr}"
        else:
            return f"No empty frames detected in {filename} - no trimming needed."
            
    except Exception as e:
        print(f"[DEV] Exception in trim_empty_frames: {str(e)}")
        return f"Error trimming empty frames from {filename}: {str(e)}"

def split_by_scenes(filename: str, sensitivity: float = 0.3, user_id: str = None) -> str:
    """Split video into scenes based on scene change detection. Sensitivity: 0.1 (very sensitive) to 1.0 (less sensitive)."""
    try:
        input_path = find_user_file(filename, user_id)
        
        if not input_path:
            return f"Error: Input file {filename} not found"
        
        base_name = os.path.splitext(filename)[0]
        user_dir = os.path.dirname(input_path)
        
        # Step 1: Detect scene changes and get timestamps
        print(f"[DEV] Detecting scenes in {filename} with sensitivity {sensitivity}")
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", f"select='gt(scene,{sensitivity})',showinfo",
            "-f", "null", "-"
        ]
        
        result = run_external_command(cmd, "External command")
        
        if result.returncode != 0:
            return f"Error detecting scenes: {result.stderr}"
        
        # Extract timestamps from showinfo output
        timestamps = [0.0]  # Always start from beginning
        print(f"[DEBUG] Scene detection stderr output:")
        print(result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr)
        
        for line in result.stderr.split('\n'):
            if 'pts_time:' in line:
                try:
                    pts_time = float(line.split('pts_time:')[1].split()[0])
                    timestamps.append(pts_time)
                    print(f"[DEBUG] Found scene change at {pts_time}s")
                except:
                    continue
        
        print(f"[DEBUG] Total timestamps found: {len(timestamps)} - {timestamps}")
        
        if len(timestamps) <= 1:
            return f"No scene changes detected in {filename}. Try lowering sensitivity (e.g., 0.1 for more sensitive detection)."
        
        # Remove duplicates and sort
        timestamps = sorted(list(set(timestamps)))
        
        print(f"[DEV] Found {len(timestamps)-1} scene changes at: {timestamps[1:]}")
        
        # Get video FPS for frame calculations
        fps_cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", input_path]
        fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
        
        fps = 30.0  # Default fallback
        if fps_result.returncode == 0 and fps_result.stdout.strip():
            try:
                fps_str = fps_result.stdout.strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
                print(f"[DEV] Detected video FPS: {fps}")
            except:
                print(f"[DEV] Could not parse FPS '{fps_str}', using default 30")
        
        # Step 2: Split video into scenes without dropping frames by default
        scene_files = []
        errors = []
        
        for i in range(len(timestamps)):
            start_time = timestamps[i]
            
            # Determine end time (next scene or end of video)
            if i < len(timestamps) - 1:
                end_time = timestamps[i + 1]
                duration = end_time - start_time
                scene_filename = f"{base_name}_scene_{i+1:02d}.mp4"
            else:
                # Last scene - go to end of video
                scene_filename = f"{base_name}_scene_{i+1:02d}.mp4"
                duration = None
            
            unique_output = generate_unique_filename(user_dir, scene_filename)
            output_path = os.path.join(user_dir, unique_output)
            
            # Build FFmpeg command for this scene with re-encoding for precision
            cmd = ["ffmpeg", "-i", input_path, "-ss", str(start_time)]
            
            if duration is not None:
                cmd.extend(["-t", str(duration)])
            
            # Re-encode for precise cuts and consistent quality
            cmd.extend([
                "-c:v", "libx264", "-crf", "18",  # High quality video
                "-c:a", "aac", "-b:a", "128k",   # Good quality audio
                "-avoid_negative_ts", "make_zero",  # Fix timestamp issues
                "-fflags", "+genpts",  # Generate proper timestamps
                "-movflags", "+faststart",  # Optimize for web playback
                output_path, "-y"
            ])
            
            print(f"[DEV] Extracting scene {i+1}: {' '.join(cmd)}")
            result = run_external_command(cmd, "External command")
            
            if result.returncode == 0:
                # Auto-trim empty frames from the scene
                print(f"[DEV] Auto-trimming empty frames from scene {i+1}")
                trimmed_filename = f"{base_name}_scene_{i+1:02d}_clean.mp4"
                user_videos_dir = get_current_user_dir()
                os.makedirs(user_videos_dir, exist_ok=True)
                trimmed_output = generate_unique_filename(user_videos_dir, trimmed_filename)
                trimmed_path = os.path.join(user_videos_dir, trimmed_output)
                
                # More aggressive detection for gray/empty frames
                # Use multiple detection methods
                
                # Method 1: blackdetect with lower threshold for gray frames
                detect_cmd = [
                    "ffmpeg", "-i", output_path,
                    "-vf", "blackdetect=d=0.01:pix_th=0.15",
                    "-f", "null", "-"
                ]
                
                detect_result = subprocess.run(detect_cmd, capture_output=True, text=True)
                
                # Method 2: Check first frame specifically for low variance (gray/uniform)
                first_frame_cmd = [
                    "ffmpeg", "-i", output_path, "-vframes", "1", "-vf", 
                    "crop=iw:ih:0:0,scale=1:1,format=gray,metadata=print:file=-",
                    "-f", "null", "-"
                ]
                
                first_frame_result = subprocess.run(first_frame_cmd, capture_output=True, text=True)
                
                # Parse blackdetect results
                black_periods = []
                for line in detect_result.stderr.split('\n'):
                    if 'blackdetect' in line and 'black_start:' in line:
                        try:
                            parts = line.split()
                            start_time = None
                            end_time = None
                            
                            for part in parts:
                                if part.startswith('black_start:'):
                                    start_time = float(part.split(':')[1])
                                elif part.startswith('black_end:'):
                                    end_time = float(part.split(':')[1])
                            
                            if start_time is not None and end_time is not None:
                                black_periods.append((start_time, end_time))
                        except:
                            continue
                
                # Get scene duration and FPS
                duration_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", output_path]
                duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
                scene_duration = float(duration_result.stdout.strip()) if duration_result.returncode == 0 else 0
                
                # Calculate trim points
                trim_start = 0.0
                trim_end = scene_duration
                
                # Always trim at least first frame if scene is long enough
                one_frame_time = 1.0 / fps
                if scene_duration > one_frame_time * 3:  # Only if scene has more than 3 frames
                    trim_start = one_frame_time  # Remove first frame by default
                
                # Find additional empty frames at beginning
                for start, end in black_periods:
                    if start <= 0.2:  # Empty frames near the beginning
                        trim_start = max(trim_start, end)
                
                # Find empty frames at end
                for start, end in black_periods:
                    if end >= scene_duration - 0.2:  # Empty frames near the end
                        trim_end = min(trim_end, start)
                
                # Apply trimming
                if trim_start > 0.01 or trim_end < scene_duration - 0.01:
                    print(f"[DEV] Trimming scene {i+1}: removing {trim_start:.3f}s from start, {scene_duration - trim_end:.3f}s from end")
                    
                    final_cmd = ["ffmpeg", "-i", output_path]
                    
                    if trim_start > 0:
                        final_cmd.extend(["-ss", str(trim_start)])
                    
                    if trim_end < scene_duration:
                        final_duration = trim_end - trim_start
                        final_cmd.extend(["-t", str(final_duration)])
                    
                    final_cmd.extend([
                        "-c:v", "libx264", "-crf", "18",
                        "-c:a", "aac", "-b:a", "128k",
                        trimmed_path, "-y"
                    ])
                    
                    final_result = subprocess.run(final_cmd, capture_output=True, text=True)
                    
                    if final_result.returncode == 0:
                        # Replace original with trimmed version
                        os.remove(output_path)
                        os.rename(trimmed_path, output_path)
                        print(f"[DEV] Scene {i+1} trimmed successfully")
                    else:
                        print(f"[DEV] Failed to trim scene {i+1}: {final_result.stderr}")
                else:
                    print(f"[DEV] Scene {i+1} - no trimming needed")
                
                scene_files.append(unique_output)
            else:
                errors.append(f"Scene {i+1}: {result.stderr}")
        
        # Prepare result message
        if scene_files:
            result_msg = f"Successfully split {filename} into {len(scene_files)} scenes: {', '.join(scene_files)}"
            if errors:
                result_msg += f"\nErrors: {'; '.join(errors)}"
            result_msg += ". Please refresh the file list."
            return result_msg
        else:
            return f"Failed to split {filename} into scenes. Errors: {'; '.join(errors)}"
            
    except Exception as e:
        print(f"[DEV] Exception in split_by_scenes: {str(e)}")
        return f"Error splitting {filename} by scenes: {str(e)}"

def delete_files_pattern(pattern: str, user_id: str = None) -> str:
    """Delete multiple files matching a pattern (e.g., '*.png', 'video*.mp4', 'all png files')."""
    try:
        import glob
        import fnmatch
        
        # Use current user directory only
        user_dir = get_current_user_dir()
        if not os.path.exists(user_dir):
            return "User directory not found"
        # Supported file extensions for safety
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                           '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                           '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                           '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf']
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                           '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                           '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f']
        all_extensions = video_extensions + image_extensions
        
        # Convert natural language to glob pattern
        pattern_lower = pattern.lower()
        
        if 'all' in pattern_lower and 'png' in pattern_lower:
            glob_pattern = "*.png"
        elif 'all' in pattern_lower and 'jpg' in pattern_lower:
            glob_pattern = "*.jpg"
        elif 'all' in pattern_lower and 'mp4' in pattern_lower:
            glob_pattern = "*.mp4"
        elif 'all' in pattern_lower and 'webm' in pattern_lower:
            glob_pattern = "*.webm"
        elif pattern.startswith('*.'):
            glob_pattern = pattern
        else:
            glob_pattern = pattern
        
        # Find matching files in user directory only
        search_path = os.path.join(user_dir, glob_pattern)
        matching_files = glob.glob(search_path)
        
        if not matching_files:
            return f"No files found matching pattern '{pattern}'"
        
        # Filter for safety - only delete media files
        safe_files = []
        for file_path in matching_files:
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in all_extensions:
                safe_files.append(file_path)
        
        if not safe_files:
            return f"No media files found matching pattern '{pattern}'"
        
        # Delete the files
        deleted_files = []
        errors = []
        
        for file_path in safe_files:
            try:
                filename = os.path.basename(file_path)
                os.remove(file_path)
                deleted_files.append(filename)
                print(f"[DEV] Deleted file: {filename}")
            except Exception as e:
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")
        
        result_msg = f"Successfully deleted {len(deleted_files)} files matching '{pattern}'"
        if deleted_files:
            result_msg += f": {', '.join(deleted_files)}"
        if errors:
            result_msg += f"\nErrors: {'; '.join(errors)}"
        result_msg += ". Please refresh the file list."
        
        return result_msg
        
    except Exception as e:
        print(f"[DEV] Exception in delete_files_pattern: {str(e)}")
        return f"Error deleting files with pattern '{pattern}': {str(e)}"

def delete_file(filename: str, user_id: str = None) -> str:
    """Delete a video or image file."""
    try:
        file_path = find_user_file(filename, user_id)
        
        if not file_path:
            return f"Error: File {filename} not found"
        
        # Safety check - only allow deletion of video and image files
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                           '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                           '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                           '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf']
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                           '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                           '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f']
        
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in video_extensions + image_extensions:
            return f"Error: Cannot delete {filename} - only video and image files can be deleted"
        
        os.remove(file_path)
        print(f"[DEV] Deleted file: {filename}")
        
        return f"Successfully deleted {filename}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in delete_file: {str(e)}")
        return f"Error deleting {filename}: {str(e)}"

def list_images(user_id: str = None) -> str:
    """List all image files in user directories."""
    try:
        videos_dir = get_current_user_dir()
        if not os.path.exists(videos_dir):
            return "Videos directory not found"
        
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                           '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                           '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f']
        images = []
        
        # Search in all user directories
        all_items = os.listdir(videos_dir)
        for item in all_items:
            item_path = os.path.join(videos_dir, item)
            if os.path.isdir(item_path):  # Any directory is a potential user directory
                try:
                    user_files = os.listdir(item_path)
                    for file in user_files:
                        if any(file.lower().endswith(ext) for ext in image_extensions):
                            file_path = os.path.join(item_path, file)
                            try:
                                stat = os.stat(file_path)
                                size = stat.st_size
                                images.append({
                                    'name': file,
                                    'size': size,
                                    'path': file_path
                                })
                            except Exception as e:
                                print(f"[DEV] Error getting info for {file}: {e}")
                except Exception as e:
                    print(f"[DEV] Error reading user directory {item}: {e}")
                    continue
        
        if not images:
            return "There are no image files currently available."
        
        result = "Available image files:\n\n"
        for image in images:
            size_mb = image['size'] / (1024 * 1024)
            result += f"{image['name']}: {size_mb:.1f}MB\n"
        
        return result.strip()
        
    except Exception as e:
        return f"Error listing images: {str(e)}"

# Frontend tool stubs for video management
def createVideo(name: Annotated[str, "Video name/title"]) -> str:
    return f"createVideo({name})"

def deleteVideo(itemId: Annotated[str, "Video id"]) -> str:
    return f"deleteVideo({itemId})"

def setVideoName(itemId: Annotated[str, "Video id"], name: Annotated[str, "New video name"]) -> str:
    return f"setVideoName({itemId}, {name})"

def setGlobalTitle(title: Annotated[str, "Global title"]) -> str:
    return f"setGlobalTitle({title})"

def setGlobalDescription(description: Annotated[str, "Global description"]) -> str:
    return f"setGlobalDescription({description})"

# Wrapper functions that automatically use current user context
def get_video_info_wrapper(filename: str) -> str:
    return get_video_info(filename, current_user_id.get())

def cut_video_wrapper(filename: str, start_time: str, duration: str, output_filename: str) -> str:
    user_id = current_user_id.get()
    print(f"[DEBUG] cut_video_wrapper called with user_id: {user_id}")
    result = cut_video(filename, start_time, duration, output_filename, user_id)
    print(f"[DEBUG] cut_video result: {result}")
    return result

def concatenate_videos_wrapper(filenames: List[str], output_filename: str, preserve_order: bool = False) -> str:
    user_id = current_user_id.get()
    print(f"[DEBUG] concatenate_videos_wrapper called with user_id: {user_id}")
    result = concatenate_videos(filenames, output_filename, preserve_order, user_id)
    print(f"[DEBUG] concatenate_videos result: {result}")
    return result

def extract_frame_wrapper(filename: str, timestamp: str, output_filename: str) -> str:
    return extract_frame(filename, timestamp, output_filename, current_user_id.get())

def list_videos_wrapper() -> str:
    print(f"[ACTION] Listing video files")
    user_id = current_user_id.get()
    result = list_videos(user_id)
    # Only log first 200 chars to avoid spam
    short_result = result[:200] + "..." if len(result) > 200 else result
    print(f"[TOOL_RESULT] list_videos: {short_result}")
    return result

    """Delete the latest (most recently created) video files."""
    try:
        print(f"[ACTION] Deleting {count} latest files")
        
        # Get all video files with their creation times
        user_dir = get_current_user_dir()
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
        
        files_with_time = []
        for file in os.listdir(user_dir):
            if any(file.lower().endswith(ext) for ext in video_extensions):
                file_path = os.path.join(user_dir, file)
                mtime = os.path.getmtime(file_path)
                files_with_time.append((file, mtime, file_path))
        
        # Sort by modification time (newest first)
        files_with_time.sort(key=lambda x: x[1], reverse=True)
        
        if len(files_with_time) < count:
            return f"Only {len(files_with_time)} files available, cannot delete {count}"
        
        deleted_files = []
        for i in range(count):
            filename, _, file_path = files_with_time[i]
            os.remove(file_path)
            deleted_files.append(filename)
            print(f"[DEV] Deleted file: {filename}")
        
        return f"Successfully deleted {count} files: {', '.join(deleted_files)}"
    
    except Exception as e:
        return f"Error deleting latest files: {str(e)}"

def delete_file_wrapper(filename: str) -> str:
    print(f"[ACTION] Deleting file: {filename}")
    user_id = current_user_id.get()
    result = delete_file(filename, user_id)
    print(f"[TOOL_RESULT] delete_file: {result}")
    return result

def delete_latest_files_wrapper(count: int = 1) -> str:
    return delete_latest_files(count)

# Custom function to log final responses
def log_ai_response(response_text: str) -> str:
    """Log AI response and return it unchanged."""
    print(f"[CHAT] AI: {response_text}")
    return response_text

def split_by_scenes_wrapper(filename: str, sensitivity: float = 0.3) -> str:
    print(f"[ACTION] Splitting video by scenes: {filename} (sensitivity: {sensitivity})")
    user_id = current_user_id.get()
    result = split_by_scenes(filename, sensitivity, user_id)
    print(f"[TOOL_RESULT] split_by_scenes: {result[:200]}..." if len(result) > 200 else f"[TOOL_RESULT] split_by_scenes: {result}")
    return result

def drop_first_frame_wrapper(filename: str) -> str:
    print(f"[ACTION] Dropping first frame from: {filename}")
    user_id = current_user_id.get()
    result = drop_first_frame(filename, user_id)
    print(f"[TOOL_RESULT] drop_first_frame: {result}")
    return result

def drop_last_frame_wrapper(filename: str) -> str:
    print(f"[ACTION] Dropping last frame from: {filename}")
    user_id = current_user_id.get()
    result = drop_last_frame(filename, user_id)
    print(f"[TOOL_RESULT] drop_last_frame: {result}")
    return result

def rename_file(old_filename: str, new_filename: str, user_id: str = None) -> str:
    """Rename a video or image file."""
    try:
        old_path = find_user_file(old_filename, user_id)
        if not old_path:
            return f"Error: File {old_filename} not found"
        
        # Get the directory of the old file
        file_dir = os.path.dirname(old_path)
        new_path = os.path.join(file_dir, new_filename)
        
        # Check if new filename already exists
        if os.path.exists(new_path):
            return f"Error: File {new_filename} already exists"
        
        # Rename the file
        os.rename(old_path, new_path)
        print(f"[DEV] Renamed {old_filename} to {new_filename}")
        
        return f"Successfully renamed {old_filename} to {new_filename}"
        
    except Exception as e:
        return f"Error renaming {old_filename}: {str(e)}"

def rename_file_wrapper(old_filename: str, new_filename: str) -> str:
    print(f"[ACTION] Renaming file: {old_filename} -> {new_filename}")
    user_id = current_user_id.get()
    result = rename_file(old_filename, new_filename, user_id)
    print(f"[TOOL_RESULT] rename_file: {result}")
    return result

def delete_files_pattern_wrapper(pattern: str) -> str:
    print(f"[ACTION] Deleting files matching pattern: {pattern}")
    user_id = current_user_id.get()
    result = delete_files_pattern(pattern, user_id)
    print(f"[TOOL_RESULT] delete_files_pattern: {result}")
    return result

# Create backend tools with wrapper functions
_backend_tools = [
    FunctionTool.from_defaults(fn=get_video_info_wrapper, name="get_video_info"),
    FunctionTool.from_defaults(fn=cut_video_wrapper, name="cut_video"),
    FunctionTool.from_defaults(fn=concatenate_videos_wrapper, name="concatenate_videos"),
    FunctionTool.from_defaults(fn=extract_frame_wrapper, name="extract_frame"),
    FunctionTool.from_defaults(fn=list_videos_wrapper, name="list_videos"),
    FunctionTool.from_defaults(fn=delete_file_wrapper, name="delete_file"),
    FunctionTool.from_defaults(fn=delete_latest_files_wrapper, name="delete_latest_files"),
    FunctionTool.from_defaults(fn=delete_files_pattern_wrapper, name="delete_files_pattern"),
    FunctionTool.from_defaults(fn=split_by_scenes_wrapper, name="split_by_scenes"),
    FunctionTool.from_defaults(fn=drop_first_frame_wrapper, name="drop_first_frame"),
    FunctionTool.from_defaults(fn=drop_last_frame_wrapper, name="drop_last_frame"),
    FunctionTool.from_defaults(fn=rename_file_wrapper, name="rename_file"),
]

print(f"Backend tools loaded: {len(_backend_tools)} video processing tools")

# Export current_user_id for server middleware
__all__ = ['agentic_chat_router', 'current_user_id']

def _create_llm():
    """Create OpenAI LLM instance, supporting both OpenAI and Azure OpenAI."""
    # Check if Azure OpenAI is configured
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    
    if azure_endpoint and azure_key:
        # Use Azure OpenAI
        return AzureOpenAI(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1"),
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
        )
    else:
        # Use regular OpenAI
        return OpenAI(model="gpt-4.1")

# Load system prompt from file
def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "system_prompt.txt")
    try:
        with open(prompt_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are PilotDirector, an AI-powered video editing assistant."

SYSTEM_PROMPT = load_system_prompt()

agentic_chat_router = get_ag_ui_workflow_router(
    llm=_create_llm(),
    frontend_tools=[
        createVideo,
        deleteVideo,
        setVideoName,
        setGlobalTitle,
        setGlobalDescription,
    ],
    backend_tools=_backend_tools,
    system_prompt=SYSTEM_PROMPT,
    initial_state={
        "items": [],
        "globalTitle": "PilotDirector",
        "globalDescription": "AI-powered video editing with natural language commands",
        "lastAction": "",
        "itemsCreated": 0,
    },
)

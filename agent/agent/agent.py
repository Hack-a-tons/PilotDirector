from typing import Annotated, List, Optional, Any
import os
import subprocess
import json
from dotenv import load_dotenv

from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool
from llama_index.protocols.ag_ui.router import get_ag_ui_workflow_router

# Load environment variables early to support local development via .env
load_dotenv()

# Video processing tools
def get_video_info(filename: str) -> str:
    """Get information about a video file using ffprobe."""
    try:
        video_path = os.path.join("../videos", filename)
        if not os.path.exists(video_path):
            return f"Error: Video file {filename} not found"
        
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", 
            "-show_format", "-show_streams", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error getting video info: {result.stderr}"
        
        data = json.loads(result.stdout)
        format_info = data.get("format", {})
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        
        # Get file stats for modification time
        stat = os.stat(video_path)
        from datetime import datetime
        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        info = {
            "duration": float(format_info.get("duration", 0)),
            "size": int(format_info.get("size", 0)),
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "modified": mod_time,
        }
        
        return f"Video info for {filename}: Duration: {info['duration']:.2f}s, Size: {info['size']} bytes ({info['size']/1024/1024:.1f} MB), Resolution: {info['width']}x{info['height']}, Modified: {info['modified']}"
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

def cut_video(filename: str, start_time: str, duration: str, output_filename: str) -> str:
    """Cut a video segment using ffmpeg."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input video {filename} not found"
        
        # Generate unique output filename
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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

def concatenate_videos(filenames: List[str], output_filename: str, preserve_order: bool = False) -> str:
    """Concatenate multiple videos using ffmpeg."""
    try:
        # Only sort alphabetically if order is not explicitly specified by user
        if preserve_order:
            sorted_filenames = filenames  # Keep user-specified order
        else:
            sorted_filenames = sorted(filenames)  # Sort alphabetically for "all videos"
        
        # Create a temporary file list
        file_list_path = "../videos/temp_filelist.txt"
        with open(file_list_path, "w") as f:
            for filename in sorted_filenames:
                video_path = os.path.join("../videos", filename)
                if os.path.exists(video_path):
                    f.write(f"file '{filename}'\n")
        
        # Generate unique output filename
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", 
            "-i", file_list_path, "-c", "copy", output_path, "-y"
        ]
        
        print(f"[DEV] Executing FFmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Clean up temp file
        if os.path.exists(file_list_path):
            os.remove(file_list_path)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error concatenating videos: {result.stderr}"
        
        return f"Successfully concatenated {len(filenames)} videos into {unique_output}. Please refresh the file list."
    except Exception as e:
        return f"Error: {str(e)}"

def extract_frame(filename: str, timestamp: str, output_filename: str) -> str:
    """Extract a frame from a video at a specific timestamp."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input video {filename} not found"
        
        # Generate unique output filename
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error extracting frame: {result.stderr}"
        
        return f"Successfully extracted frame from {filename} at {timestamp}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in extract_frame: {str(e)}")
        return f"Error extracting frame from {filename}: {str(e)}"

def list_videos() -> str:
    """List all video files in the videos directory with basic info."""
    try:
        print(f"[DEV] list_videos() called - starting execution")
        videos_dir = "../videos"
        if not os.path.exists(videos_dir):
            print(f"[DEV] Videos directory not found: {videos_dir}")
            return "Videos directory not found"
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                           '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                           '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                           '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf']
        videos = []
        
        all_files = os.listdir(videos_dir)
        print(f"[DEV] Found {len(all_files)} total files in directory")
        
        for file in all_files:
            if any(file.lower().endswith(ext) for ext in video_extensions):
                print(f"[DEV] Processing video file: {file}")
                file_path = os.path.join(videos_dir, file)
                
                # Get basic info for each video
                try:
                    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
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
                                if '/' in fps_str:
                                    num, den = fps_str.split('/')
                                    fps = float(num) / float(den)
                                else:
                                    fps = float(fps_str)
                                fps = round(fps, 2)
                            except:
                                fps = 30.0
                        
                        frame_count = int(duration * fps) if duration > 0 else 0
                        
                        # Get modification time
                        stat = os.stat(file_path)
                        from datetime import datetime
                        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        
                        videos.append({
                            'name': file,
                            'duration': duration,
                            'size': size,
                            'width': width,
                            'height': height,
                            'fps': fps,
                            'frame_count': frame_count,
                            'modified': mod_time
                        })
                    else:
                        videos.append({'name': file, 'duration': 0, 'size': 0, 'width': 0, 'height': 0, 'fps': 0, 'frame_count': 0, 'modified': 'unknown'})
                except:
                    videos.append({'name': file, 'duration': 0, 'size': 0, 'width': 0, 'height': 0, 'fps': 0, 'frame_count': 0, 'modified': 'unknown'})
        
        if not videos:
            return "No video files found"
        
        # Sort by modification time (most recent first)
        videos.sort(key=lambda x: x['modified'], reverse=True)
        
        result = "Available videos:\n"
        for video in videos:
            size_mb = video['size'] / 1024 / 1024 if video['size'] > 0 else 0
            resolution = f"{video['width']}x{video['height']}" if video['width'] > 0 else "unknown"
            fps_info = f" ({video['frame_count']}f @{video['fps']}fps)" if video['fps'] > 0 else ""
            result += f"- {video['name']}: {video['duration']:.1f}s{fps_info}, {size_mb:.1f}MB, {resolution}, modified: {video['modified']}\n"
        
        return result.strip()
    except Exception as e:
        return f"Error listing videos: {str(e)}"

def resize_media(filename: str, output_filename: str, width: int = 0, height: int = 0, scale: str = "") -> str:
    """Resize video or image. Use width/height for exact size, or scale for proportional (e.g. '0.5' for 50%)."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error resizing: {result.stderr}"
        
        return f"Successfully resized {filename}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in resize_media: {str(e)}")
        return f"Error resizing {filename}: {str(e)}"

def change_aspect_ratio(filename: str, output_filename: str, ratio: str, method: str = "pad") -> str:
    """Change aspect ratio of video/image. Ratio like '16:9', '4:3', '1:1'. Method: 'pad' (add bars) or 'crop'."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error changing aspect ratio: {result.stderr}"
        
        return f"Successfully changed aspect ratio of {filename} to {ratio}, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in change_aspect_ratio: {str(e)}")
        return f"Error changing aspect ratio of {filename}: {str(e)}"

def rotate_media(filename: str, output_filename: str, angle: int) -> str:
    """Rotate video or image by specified angle (90, 180, 270 degrees)."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error rotating: {result.stderr}"
        
        return f"Successfully rotated {filename} by {angle} degrees, saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in rotate_media: {str(e)}")
        return f"Error rotating {filename}: {str(e)}"

def recode_video(filename: str, output_filename: str, format: str = "mp4", quality: str = "medium") -> str:
    """Recode video to different format/quality. Format: mp4, webm, avi. Quality: high, medium, low, 720p, 1080p."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        # Auto-generate output filename if not provided with extension
        if not output_filename.endswith(('.mp4', '.webm', '.avi', '.mov')):
            base_name = os.path.splitext(output_filename)[0]
            output_filename = f"{base_name}.{format}"
        
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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

def crop_image(filename: str, output_filename: str, crop_type: str = "auto") -> str:
    """Crop an image to remove black bars or borders. crop_type: 'auto', 'top-bottom', 'left-right', or 'manual'."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input image {filename} not found"
        
        # Generate unique output filename
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
        if crop_type.lower() in ['auto', 'black', 'letterbox']:
            # Try multiple sensitivity levels for cropdetect
            for threshold in [24, 16, 8, 4]:
                cmd = [
                    "ffmpeg", "-i", input_path, 
                    "-vf", f"cropdetect={threshold}:16:0", 
                    "-f", "null", "-"
                ]
                
                print(f"[DEV] Detecting crop area (threshold {threshold}): {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[DEV] FFmpeg error: {result.stderr}")
            return f"Error cropping image: {result.stderr}"
        
        return f"Successfully cropped {filename} ({crop_type}), saved as {unique_output}. Please refresh the file list."
    except Exception as e:
        print(f"[DEV] Exception in crop_image: {str(e)}")
        return f"Error cropping image {filename}: {str(e)}"

def trim_empty_frames(filename: str, output_filename: str = None) -> str:
    """Detect and remove empty/black frames from the beginning and end of a video."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        if not output_filename:
            base_name = os.path.splitext(filename)[0]
            output_filename = f"{base_name}_trimmed.mp4"
        
        unique_output = generate_unique_filename("../videos", output_filename)
        output_path = os.path.join("../videos", unique_output)
        
        print(f"[DEV] Detecting empty frames in {filename}")
        
        # Detect black frames at start and end
        # Use blackdetect filter to find black/empty frames
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", "blackdetect=d=0.1:pix_th=0.1",
            "-f", "null", "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return f"Successfully trimmed empty frames from {filename} → {unique_output}. Removed {trim_start:.3f}s from start and {total_duration - trim_end:.3f}s from end."
            else:
                return f"Error trimming {filename}: {result.stderr}"
        else:
            return f"No empty frames detected in {filename} - no trimming needed."
            
    except Exception as e:
        print(f"[DEV] Exception in trim_empty_frames: {str(e)}")
        return f"Error trimming empty frames from {filename}: {str(e)}"

def split_by_scenes(filename: str, sensitivity: float = 0.3) -> str:
    """Split video into scenes based on scene change detection. Sensitivity: 0.1 (very sensitive) to 1.0 (less sensitive)."""
    try:
        input_path = os.path.join("../videos", filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input file {filename} not found"
        
        base_name = os.path.splitext(filename)[0]
        
        # Step 1: Detect scene changes and get timestamps
        print(f"[DEV] Detecting scenes in {filename} with sensitivity {sensitivity}")
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", f"select='gt(scene,{sensitivity})',showinfo",
            "-f", "null", "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error detecting scenes: {result.stderr}"
        
        # Extract timestamps from showinfo output
        timestamps = [0.0]  # Always start from beginning
        for line in result.stderr.split('\n'):
            if 'pts_time:' in line:
                try:
                    pts_time = float(line.split('pts_time:')[1].split()[0])
                    timestamps.append(pts_time)
                except:
                    continue
        
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
            
            unique_output = generate_unique_filename("../videos", scene_filename)
            output_path = os.path.join("../videos", unique_output)
            
            # Build FFmpeg command for this scene with re-encoding for precision
            cmd = ["ffmpeg", "-i", input_path, "-ss", str(start_time)]
            
            if duration is not None:
                cmd.extend(["-t", str(duration)])
            
            # Re-encode for precise cuts and consistent quality
            cmd.extend([
                "-c:v", "libx264", "-crf", "18",  # High quality video
                "-c:a", "aac", "-b:a", "128k",   # Good quality audio
                "-avoid_negative_ts", "make_zero",  # Fix timestamp issues
                output_path, "-y"
            ])
            
            print(f"[DEV] Extracting scene {i+1}: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Auto-trim empty frames from the scene
                print(f"[DEV] Auto-trimming empty frames from scene {i+1}")
                trimmed_filename = f"{base_name}_scene_{i+1:02d}_clean.mp4"
                trimmed_output = generate_unique_filename("../videos", trimmed_filename)
                trimmed_path = os.path.join("../videos", trimmed_output)
                
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

def delete_files_pattern(pattern: str) -> str:
    """Delete multiple files matching a pattern (e.g., '*.png', 'video*.mp4', 'all png files')."""
    try:
        import glob
        import fnmatch
        
        videos_dir = "../videos"
        if not os.path.exists(videos_dir):
            return "Videos directory not found"
        
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
        
        # Find matching files
        search_path = os.path.join(videos_dir, glob_pattern)
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

def delete_file(filename: str) -> str:
    """Delete a video or image file."""
    try:
        file_path = os.path.join("../videos", filename)
        
        if not os.path.exists(file_path):
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

def list_images() -> str:
    """List all image files in the videos directory."""
    try:
        videos_dir = "../videos"
        if not os.path.exists(videos_dir):
            return "Videos directory not found"
        
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                           '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                           '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f']
        images = []
        
        for file in os.listdir(videos_dir):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                file_path = os.path.join(videos_dir, file)
                
                try:
                    # Get image info using ffprobe
                    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", file_path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        stream = data.get("streams", [{}])[0]
                        width = stream.get("width", 0)
                        height = stream.get("height", 0)
                        
                        # Get file size and modification time
                        stat = os.stat(file_path)
                        size = stat.st_size
                        from datetime import datetime
                        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        
                        images.append({
                            'name': file,
                            'width': width,
                            'height': height,
                            'size': size,
                            'modified': mod_time
                        })
                    else:
                        stat = os.stat(file_path)
                        images.append({
                            'name': file,
                            'width': 0,
                            'height': 0,
                            'size': stat.st_size,
                            'modified': 'unknown'
                        })
                except:
                    images.append({'name': file, 'width': 0, 'height': 0, 'size': 0, 'modified': 'unknown'})
        
        if not images:
            return "No image files found"
        
        # Sort by modification time (most recent first)
        images.sort(key=lambda x: x['modified'], reverse=True)
        
        result = "Available images:\n"
        for image in images:
            size_kb = image['size'] / 1024 if image['size'] > 0 else 0
            resolution = f"{image['width']}x{image['height']}" if image['width'] > 0 else "unknown"
            result += f"- {image['name']}: {resolution}, {size_kb:.1f}KB, modified: {image['modified']}\n"
        
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

# Create backend tools
_backend_tools = [
    FunctionTool.from_defaults(fn=get_video_info),
    FunctionTool.from_defaults(fn=cut_video),
    FunctionTool.from_defaults(fn=concatenate_videos),
    FunctionTool.from_defaults(fn=extract_frame),
    FunctionTool.from_defaults(fn=resize_media),
    FunctionTool.from_defaults(fn=change_aspect_ratio),
    FunctionTool.from_defaults(fn=rotate_media),
    FunctionTool.from_defaults(fn=recode_video),
    FunctionTool.from_defaults(fn=crop_image),
    FunctionTool.from_defaults(fn=trim_empty_frames),
    FunctionTool.from_defaults(fn=split_by_scenes),
    FunctionTool.from_defaults(fn=list_videos),
    FunctionTool.from_defaults(fn=list_images),
    FunctionTool.from_defaults(fn=delete_file),
    FunctionTool.from_defaults(fn=delete_files_pattern),
]

print(f"Backend tools loaded: {len(_backend_tools)} video processing tools")

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

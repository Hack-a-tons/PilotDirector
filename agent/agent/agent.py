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
        import os
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

def cut_video(filename: str, start_time: str, duration: str, output_filename: str) -> str:
    """Cut a video segment using ffmpeg."""
    try:
        input_path = os.path.join("../videos", filename)
        output_path = os.path.join("../videos", output_filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input video {filename} not found"
        
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
        
        cmd = [
            "ffmpeg", "-i", input_path, "-ss", start_time, 
            "-t", duration, "-c", "copy", output_path, "-y"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error cutting video: {result.stderr}"
        
        # Verify output file was created and has reasonable size
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            if size < 1000:  # Less than 1KB is suspicious
                return f"Warning: Output file {output_filename} created but very small ({size} bytes). Check if cut parameters are correct."
        
        return f"Successfully cut {filename} from {start_time}s for {duration}s, saved as {output_filename}"
    except Exception as e:
        return f"Error cutting video {filename}: {str(e)}"

def concatenate_videos(filenames: List[str], output_filename: str) -> str:
    """Concatenate multiple videos using ffmpeg."""
    try:
        # Create a temporary file list
        file_list_path = "../videos/temp_filelist.txt"
        with open(file_list_path, "w") as f:
            for filename in filenames:
                video_path = os.path.join("../videos", filename)
                if os.path.exists(video_path):
                    f.write(f"file '{filename}'\n")
        
        output_path = os.path.join("../videos", output_filename)
        
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", 
            "-i", file_list_path, "-c", "copy", output_path, "-y"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Clean up temp file
        if os.path.exists(file_list_path):
            os.remove(file_list_path)
        
        if result.returncode != 0:
            return f"Error concatenating videos: {result.stderr}"
        
        return f"Successfully concatenated {len(filenames)} videos into {output_filename}"
    except Exception as e:
        return f"Error: {str(e)}"

def extract_frame(filename: str, timestamp: str, output_filename: str) -> str:
    """Extract a frame from a video at a specific timestamp."""
    try:
        input_path = os.path.join("../videos", filename)
        output_path = os.path.join("../videos", output_filename)
        
        if not os.path.exists(input_path):
            return f"Error: Input video {filename} not found"
        
        # Get video duration first to validate timestamp
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
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error extracting frame: {result.stderr}"
        
        return f"Successfully extracted frame from {filename} at {timestamp}s, saved as {output_filename}"
    except Exception as e:
        return f"Error extracting frame from {filename}: {str(e)}"

def list_videos() -> str:
    """List all video files in the videos directory with basic info."""
    try:
        videos_dir = "../videos"
        if not os.path.exists(videos_dir):
            return "Videos directory not found"
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        videos = []
        
        for file in os.listdir(videos_dir):
            if any(file.lower().endswith(ext) for ext in video_extensions):
                file_path = os.path.join(videos_dir, file)
                
                # Get basic info for each video
                try:
                    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size", "-of", "csv=p=0", file_path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 0 and ',' in lines[0]:
                            duration_str, size_str = lines[0].split(',')
                            duration = float(duration_str) if duration_str else 0
                            size = int(size_str) if size_str else 0
                            
                            # Get modification time
                            stat = os.stat(file_path)
                            from datetime import datetime
                            mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                            
                            videos.append({
                                'name': file,
                                'duration': duration,
                                'size': size,
                                'modified': mod_time
                            })
                        else:
                            videos.append({'name': file, 'duration': 0, 'size': 0, 'modified': 'unknown'})
                    else:
                        videos.append({'name': file, 'duration': 0, 'size': 0, 'modified': 'unknown'})
                except:
                    videos.append({'name': file, 'duration': 0, 'size': 0, 'modified': 'unknown'})
        
        if not videos:
            return "No video files found"
        
        # Sort by modification time (most recent first)
        videos.sort(key=lambda x: x['modified'], reverse=True)
        
        result = "Available videos:\n"
        for video in videos:
            size_mb = video['size'] / 1024 / 1024 if video['size'] > 0 else 0
            result += f"- {video['name']}: {video['duration']:.1f}s, {size_mb:.1f}MB, modified: {video['modified']}\n"
        
        return result.strip()
    except Exception as e:
        return f"Error listing videos: {str(e)}"

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
    FunctionTool.from_defaults(fn=list_videos),
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

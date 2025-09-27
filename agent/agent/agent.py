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
            return f"Video file {filename} not found"
        
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
        
        info = {
            "duration": float(format_info.get("duration", 0)),
            "size": int(format_info.get("size", 0)),
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
        }
        
        return f"Video info for {filename}: Duration: {info['duration']:.2f}s, Size: {info['size']} bytes, Resolution: {info['width']}x{info['height']}"
    except Exception as e:
        return f"Error: {str(e)}"

def cut_video(filename: str, start_time: str, duration: str, output_filename: str) -> str:
    """Cut a video segment using ffmpeg."""
    try:
        input_path = os.path.join("../videos", filename)
        output_path = os.path.join("../videos", output_filename)
        
        if not os.path.exists(input_path):
            return f"Input video {filename} not found"
        
        cmd = [
            "ffmpeg", "-i", input_path, "-ss", start_time, 
            "-t", duration, "-c", "copy", output_path, "-y"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error cutting video: {result.stderr}"
        
        return f"Successfully cut {filename} from {start_time} for {duration} seconds, saved as {output_filename}"
    except Exception as e:
        return f"Error: {str(e)}"

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
            return f"Input video {filename} not found"
        
        cmd = [
            "ffmpeg", "-i", input_path, "-ss", timestamp, 
            "-vframes", "1", output_path, "-y"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error extracting frame: {result.stderr}"
        
        return f"Successfully extracted frame from {filename} at {timestamp}, saved as {output_filename}"
    except Exception as e:
        return f"Error: {str(e)}"

def list_videos() -> str:
    """List all video files in the videos directory."""
    try:
        videos_dir = "../videos"
        if not os.path.exists(videos_dir):
            return "Videos directory not found"
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        videos = []
        
        for file in os.listdir(videos_dir):
            if any(file.lower().endswith(ext) for ext in video_extensions):
                videos.append(file)
        
        if not videos:
            return "No video files found"
        
        return f"Available videos: {', '.join(videos)}"
    except Exception as e:
        return f"Error: {str(e)}"

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

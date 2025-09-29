#!/usr/bin/env bash

# Check if FFmpeg is installed
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "Error: ffprobe (FFmpeg) is not installed. Please install FFmpeg."
  exit 1
fi

# Check if at least one argument is provided
if [ $# -eq 0 ]; then
  echo "Usage: $0 <video_file(s) or pattern>"
  exit 1
fi

# Function to get file size in MB
get_file_size() {
  local file="$1"
  # Detect system type (Linux or macOS/BSD)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: Use stat to get size in bytes, convert to MB
    size_bytes=$(stat -f %z "$file" 2>/dev/null)
    size_mb=$(echo "scale=2; $size_bytes / 1048576" | bc -l)
  else
    # Linux: Use ls -l --block-size=1 to get size in bytes, convert to MB
    size_bytes=$(ls -l --block-size=1 "$file" 2>/dev/null | awk '{print $5}')
    size_mb=$(echo "scale=2; $size_bytes / 1048576" | bc -l)
  fi
  # If size is empty or invalid, set to 0
  if [ -z "$size_mb" ] || [ "$size_mb" == ".00" ]; then
    size_mb="0.00"
  fi
  echo "$size_mb"
}

# Loop through all provided files or expanded patterns (e.g., videos/*.mp4)
for input_file in "$@"; do
  # Skip if file doesn't exist or is not a file
  [ -f "$input_file" ] || continue

  # Get FPS (r_frame_rate, evaluated as a decimal)
  fps=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null | bc -l)
  # If fps is empty (invalid video), skip
  [ -z "$fps" ] && continue

  # Get duration in seconds
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null)
  # If duration is empty, skip
  [ -z "$duration" ] && continue

  # Get frame count using nb_read_packets
  frames=$(ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null)
  # If frames is empty, skip
  [ -z "$frames" ] && continue

  # Get file size in MB
  size=$(get_file_size "$input_file")

  # Print formatted output: filename duration frames fps size
  printf "%s %.2fs %df %.2ffps %.2fMB\n" "$input_file" "$duration" "$frames" "$fps" "$size"
done

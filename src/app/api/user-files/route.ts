import { NextRequest, NextResponse } from 'next/server';
import { readdir, stat, mkdir } from 'fs/promises';
import { join } from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

function getUserId(request: NextRequest): string {
  // Get user ID from header (set by frontend)
  const userId = request.headers.get('x-user-id');
  if (!userId) {
    throw new Error('User ID required');
  }
  return userId;
}

async function ensureUserDirectory(userId: string): Promise<string> {
  const userDir = join(process.cwd(), 'videos', userId);
  try {
    await mkdir(userDir, { recursive: true });
  } catch {
    // Directory might already exist
  }
  return userDir;
}

export async function GET(request: NextRequest) {
  try {
    const userId = getUserId(request);
    const userDir = await ensureUserDirectory(userId);
    
    const files = await readdir(userDir);
    
    const videoExtensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                            '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                            '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                            '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf'];
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                            '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                            '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f'];

    const filePromises = files.map(async (file) => {
      try {
        const filePath = join(userDir, file);
        const fileStat = await stat(filePath);
        const isVideo = videoExtensions.some(ext => file.toLowerCase().endsWith(ext));
        const isImage = imageExtensions.some(ext => file.toLowerCase().endsWith(ext));
        
        if (!isVideo && !isImage) return null;

        let metadata: {
          name: string;
          type: string;
          size: number;
          modified: string;
          duration?: number;
          width?: number;
          height?: number;
          fps?: number;
          frameCount?: number;
        } = {
          name: file,
          type: isVideo ? 'video' : 'image',
          size: fileStat.size,
          modified: fileStat.mtime.toISOString(),
        };

        // Get video/image metadata using ffprobe
        try {
          const { stdout } = await execAsync(`ffprobe -v quiet -print_format json -show_format -show_streams "${filePath}"`);
          const data = JSON.parse(stdout);
          
          if (isVideo) {
            const format = data.format || {};
            const videoStream = data.streams?.find((s: { codec_type: string }) => s.codec_type === 'video') || {};
            
            // Get actual FPS
            let fps = 30; // Default
            if (videoStream.r_frame_rate) {
              const [num, den] = videoStream.r_frame_rate.split('/').map(Number);
              if (den && den > 0) {
                fps = Math.round((num / den) * 100) / 100; // Round to 2 decimals
              }
            }
            
            const duration = parseFloat(format.duration || '0');
            const frameCount = Math.round(duration * fps);
            
            metadata = {
              ...metadata,
              duration,
              width: videoStream.width || 0,
              height: videoStream.height || 0,
              fps,
              frameCount,
            };
          } else {
            const stream = data.streams?.[0] || {};
            metadata = {
              ...metadata,
              width: stream.width || 0,
              height: stream.height || 0,
            };
          }
        } catch (error) {
          console.error(`Error getting metadata for ${file}:`, error);
        }

        return metadata;
      } catch (error) {
        console.error(`Error processing file ${file}:`, error);
        return null;
      }
    });

    const results = await Promise.all(filePromises);
    const validFiles = results.filter(file => file !== null);

    return NextResponse.json({ files: validFiles });
  } catch (error) {
    console.error('Error listing user files:', error);
    return NextResponse.json({ error: 'Failed to list files' }, { status: 500 });
  }
}

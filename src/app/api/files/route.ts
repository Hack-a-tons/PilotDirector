import { NextResponse } from 'next/server';
import { readdir, stat } from 'fs/promises';
import { join } from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export async function GET() {
  try {
    const videosDir = join(process.cwd(), 'videos');
    const files = await readdir(videosDir);
    
    const videoExtensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', 
                            '.m4v', '.3gp', '.ogv', '.ts', '.mts', '.m2ts', '.vob', 
                            '.asf', '.rm', '.rmvb', '.divx', '.xvid', '.f4v', '.mpg', 
                            '.mpeg', '.m1v', '.m2v', '.mpe', '.mpv', '.mp2', '.mxf'];
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', 
                            '.webp', '.svg', '.ico', '.psd', '.raw', '.cr2', '.nef', 
                            '.arw', '.dng', '.orf', '.rw2', '.pef', '.srw', '.x3f'];
    
    const fileData = await Promise.all(
      files.map(async (file) => {
        const filePath = join(videosDir, file);
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
        } = {
          name: file,
          type: isVideo ? 'video' : 'image',
          size: fileStat.size,
          modified: fileStat.mtime.toISOString(),
        };
        
        try {
          const { stdout } = await execAsync(`ffprobe -v quiet -print_format json -show_format -show_streams "${filePath}"`);
          const data = JSON.parse(stdout);
          
          if (isVideo) {
            const format = data.format || {};
            const videoStream = data.streams?.find((s: { codec_type: string }) => s.codec_type === 'video') || {};
            metadata = {
              ...metadata,
              duration: parseFloat(format.duration || '0'),
              width: videoStream.width || 0,
              height: videoStream.height || 0,
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
      })
    );
    
    const validFiles = fileData.filter((file): file is NonNullable<typeof file> => Boolean(file));
    validFiles.sort((a, b) => a.name.localeCompare(b.name));
    
    return NextResponse.json(validFiles);
  } catch (error) {
    console.error('Error reading files:', error);
    return NextResponse.json({ error: 'Failed to read files' }, { status: 500 });
  }
}

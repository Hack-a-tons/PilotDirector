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
    
    const videoExtensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'];
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'];
    
    const fileData = await Promise.all(
      files.map(async (file) => {
        const filePath = join(videosDir, file);
        const fileStat = await stat(filePath);
        const isVideo = videoExtensions.some(ext => file.toLowerCase().endsWith(ext));
        const isImage = imageExtensions.some(ext => file.toLowerCase().endsWith(ext));
        
        if (!isVideo && !isImage) return null;
        
        let metadata = {
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
            const videoStream = data.streams?.find((s: any) => s.codec_type === 'video') || {};
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
    
    const validFiles = fileData.filter(Boolean);
    validFiles.sort((a, b) => a.name.localeCompare(b.name));
    
    return NextResponse.json(validFiles);
  } catch (error) {
    console.error('Error reading files:', error);
    return NextResponse.json({ error: 'Failed to read files' }, { status: 500 });
  }
}

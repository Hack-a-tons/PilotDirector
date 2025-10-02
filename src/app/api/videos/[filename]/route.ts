import { NextRequest, NextResponse } from 'next/server';
import { createReadStream, existsSync, statSync, readdirSync } from 'fs';
import { join } from 'path';

function getUserId(request: NextRequest): string {
  const userId = request.headers.get('x-user-id');
  if (!userId) {
    throw new Error('User ID required');
  }
  return userId;
}

function findFileInUserDirectories(filename: string): string | null {
  const videosDir = join(process.cwd(), 'videos');
  
  try {
    // Get all user directories
    const userDirs = readdirSync(videosDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);
    
    // Check each user directory for the file
    for (const userDir of userDirs) {
      const filePath = join(videosDir, userDir, filename);
      if (existsSync(filePath)) {
        return filePath;
      }
    }
  } catch (error) {
    console.error('Error searching user directories:', error);
  }
  
  return null;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ filename: string }> }
) {
  try {
    const { filename } = await params;
    
    // Try to get user-specific file first
    let filePath: string | null = null;
    
    try {
      const userId = getUserId(request);
      filePath = join(process.cwd(), 'videos', userId, filename);
      
      if (!existsSync(filePath)) {
        filePath = null;
      }
    } catch (error) {
      // No user ID provided, search all directories
      filePath = findFileInUserDirectories(filename);
    }
    
    // Fallback to root videos directory
    if (!filePath) {
      filePath = join(process.cwd(), 'videos', filename);
      if (!existsSync(filePath)) {
        return new NextResponse('File not found', { status: 404 });
      }
    }

    const stat = statSync(filePath);
    const fileSize = stat.size;
    
    // Determine content type
    const ext = filename.toLowerCase().split('.').pop();
    let contentType = 'application/octet-stream';
    
    if (['mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv'].includes(ext || '')) {
      contentType = 'video/mp4';
    } else if (['png'].includes(ext || '')) {
      contentType = 'image/png';
    } else if (['jpg', 'jpeg'].includes(ext || '')) {
      contentType = 'image/jpeg';
    } else if (['gif'].includes(ext || '')) {
      contentType = 'image/gif';
    }

    // Handle range requests for videos
    const range = request.headers.get('range');
    if (range && contentType.startsWith('video/')) {
      const parts = range.replace(/bytes=/, "").split("-");
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
      const chunksize = (end - start) + 1;
      
      const stream = createReadStream(filePath, { start, end });
      
      return new NextResponse(stream as unknown as ReadableStream, {
        status: 206,
        headers: {
          'Content-Range': `bytes ${start}-${end}/${fileSize}`,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunksize.toString(),
          'Content-Type': contentType,
        },
      });
    } else {
      // Serve full file (for images or non-range video requests)
      const stream = createReadStream(filePath);
      
      return new NextResponse(stream as unknown as ReadableStream, {
        headers: {
          'Content-Length': fileSize.toString(),
          'Content-Type': contentType,
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }
  } catch (error) {
    console.error('Error serving file:', error);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}

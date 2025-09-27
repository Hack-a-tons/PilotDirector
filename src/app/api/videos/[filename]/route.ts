import { NextRequest, NextResponse } from 'next/server';
import { createReadStream, existsSync, statSync } from 'fs';
import { join } from 'path';

export async function GET(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  try {
    const { filename } = await params;
    const filePath = join(process.cwd(), 'videos', filename);
    
    if (!existsSync(filePath)) {
      return new NextResponse('File not found', { status: 404 });
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
      
      return new NextResponse(stream as any, {
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
      
      return new NextResponse(stream as any, {
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

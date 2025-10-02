import { NextRequest, NextResponse } from 'next/server';
import { writeFile, mkdir } from 'fs/promises';
import { join } from 'path';

function getUserId(request: NextRequest): string {
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

export async function POST(request: NextRequest) {
  try {
    const userId = getUserId(request);
    const userDir = await ensureUserDirectory(userId);
    
    const formData = await request.formData();
    const file = formData.get('file') as File;
    
    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    // Validate file type
    const allowedTypes = [
      // Videos
      'video/mp4', 'video/avi', 'video/mov', 'video/mkv', 'video/wmv', 
      'video/webm', 'video/quicktime',
      // Images  
      'image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/bmp',
      'image/tiff', 'image/webp'
    ];

    if (!allowedTypes.includes(file.type)) {
      return NextResponse.json({ 
        error: 'Invalid file type. Only videos and images are allowed.' 
      }, { status: 400 });
    }

    // Generate safe filename
    const timestamp = Date.now();
    const safeName = file.name.replace(/[^a-zA-Z0-9.-]/g, '_');
    const filename = `${timestamp}_${safeName}`;
    
    const filePath = join(userDir, filename);
    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    await writeFile(filePath, buffer);

    return NextResponse.json({ 
      message: 'File uploaded successfully',
      filename: filename,
      size: file.size,
      type: file.type
    });

  } catch (error) {
    console.error('Upload error:', error);
    return NextResponse.json({ 
      error: 'Failed to upload file' 
    }, { status: 500 });
  }
}

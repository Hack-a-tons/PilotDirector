import { promises as fs } from 'fs';
import path from 'path';

const VIDEOS_DIR = 'videos';

async function getUniqueFilename(targetDir: string, filename: string): Promise<string> {
  const targetPath = path.join(targetDir, filename);
  
  try {
    await fs.access(targetPath);
  } catch {
    // File doesn't exist, use original name
    return filename;
  }
  
  const { name, ext } = path.parse(filename);
  let counter = 1;
  
  while (true) {
    const newFilename = `${name}_${counter}${ext}`;
    const newPath = path.join(targetDir, newFilename);
    
    try {
      await fs.access(newPath);
      counter++;
    } catch {
      return newFilename;
    }
  }
}

export async function migrateAnonymousToAuthorized(
  anonymousFolder: string, 
  authorizedUid: string
): Promise<{ success: boolean; message: string; filesMoved: number }> {
  const anonymousPath = path.join(VIDEOS_DIR, anonymousFolder);
  const authorizedPath = path.join(VIDEOS_DIR, authorizedUid);
  
  try {
    // Check if anonymous folder is already a symlink
    const stats = await fs.lstat(anonymousPath);
    if (stats.isSymbolicLink()) {
      return { success: true, message: `${anonymousFolder} is already symlinked`, filesMoved: 0 };
    }
    
    // Create authorized folder if it doesn't exist
    await fs.mkdir(authorizedPath, { recursive: true });
    
    // Get files from anonymous folder
    const items = await fs.readdir(anonymousPath, { withFileTypes: true });
    const files = items.filter(item => item.isFile());
    
    let filesMoved = 0;
    
    // Move each file
    for (const file of files) {
      const sourcePath = path.join(anonymousPath, file.name);
      const uniqueFilename = await getUniqueFilename(authorizedPath, file.name);
      const targetPath = path.join(authorizedPath, uniqueFilename);
      
      await fs.rename(sourcePath, targetPath);
      filesMoved++;
    }
    
    // Remove empty anonymous folder
    const remainingItems = await fs.readdir(anonymousPath);
    if (remainingItems.length === 0) {
      await fs.rmdir(anonymousPath);
    }
    
    // Create symlink
    await fs.symlink(authorizedUid, anonymousPath);
    
    return { 
      success: true, 
      message: `Migration complete: ${filesMoved} files moved`, 
      filesMoved 
    };
    
  } catch (error) {
    return { 
      success: false, 
      message: `Migration failed: ${error instanceof Error ? error.message : 'Unknown error'}`, 
      filesMoved: 0 
    };
  }
}

export function isAnonymousFolder(folderName: string): boolean {
  return folderName.startsWith('browser-');
}

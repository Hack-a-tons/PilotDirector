import React, { useEffect, useState } from 'react';
import { Play, Image as ImageIcon, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Image from 'next/image';

interface FileItem {
  name: string;
  type: 'video' | 'image';
  size: number;
  modified: string;
  duration?: number;
  width?: number;
  height?: number;
}

export default function FileBrowser() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchFiles = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/files');
      const data = await response.json();
      setFiles(data);
    } catch (error) {
      console.error('Error fetching files:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Files</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchFiles}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <div className="text-center text-gray-500">Loading files...</div>
        ) : files.length === 0 ? (
          <div className="text-center text-gray-500">No files found</div>
        ) : (
          files.map((file) => (
            <div key={file.name} className="bg-gray-50 rounded-lg p-3">
              {/* Preview */}
              <div className="relative mb-2">
                {file.type === 'video' ? (
                  <div className="relative">
                    <video
                      className="w-full h-32 object-cover rounded bg-gray-200"
                      preload="metadata"
                      muted
                    >
                      <source src={`/api/videos/${file.name}#t=0.1`} />
                    </video>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="bg-black bg-opacity-50 rounded-full p-2">
                        <Play className="h-6 w-6 text-white" />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="relative">
                    <Image
                      src={`/api/videos/${file.name}`}
                      alt={file.name}
                      width={320}
                      height={128}
                      className="w-full h-32 object-cover rounded bg-gray-200"
                    />
                    <div className="hidden flex items-center justify-center h-32 bg-gray-200 rounded">
                      <ImageIcon className="h-8 w-8 text-gray-400" />
                    </div>
                  </div>
                )}
              </div>

              {/* File Info */}
              <div className="space-y-1">
                <div className="font-medium text-sm text-gray-900 truncate" title={file.name}>
                  {file.name}
                </div>
                
                <div className="text-xs text-gray-600 space-y-0.5">
                  {file.width && file.height && (
                    <div>{file.width}×{file.height}</div>
                  )}
                  
                  {file.type === 'video' && file.duration && (
                    <div>Duration: {formatDuration(file.duration)}</div>
                  )}
                  
                  <div>Size: {formatSize(file.size)}</div>
                </div>
              </div>

              {/* Video Player (expandable) */}
              {file.type === 'video' && (
                <div className="mt-2">
                  <video
                    controls
                    className="w-full rounded"
                    preload="metadata"
                  >
                    <source src={`/api/videos/${file.name}`} />
                    Your browser does not support the video tag.
                  </video>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

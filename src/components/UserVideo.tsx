import { useUser } from "@/contexts/UserContext";
import { FrameByFramePlayer } from "./FrameByFramePlayer";
import Image from "next/image";
import { useEffect, useState, useRef } from "react";
import { Download } from "lucide-react";

interface UserVideoProps {
  filename: string;
  type: 'video' | 'image';
  fps?: number;
  frameCount?: number;
  className?: string;
}

export function UserVideo({ filename, type, fps, frameCount, className }: UserVideoProps) {
  const { userId } = useUser();
  const [videoUrl, setVideoUrl] = useState<string>('');
  const currentUrlRef = useRef<string>('');

  useEffect(() => {
    // Create a blob URL with proper headers
    const fetchVideo = async () => {
      try {
        const response = await fetch(`/api/videos/${filename}`, {
          headers: {
            'x-user-id': userId
          }
        });
        
        if (response.ok) {
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          currentUrlRef.current = url;
          setVideoUrl(url);
        }
      } catch (error) {
        console.error('Error fetching video:', error);
      }
    };

    fetchVideo();

    // Cleanup blob URL on unmount
    return () => {
      if (currentUrlRef.current) {
        URL.revokeObjectURL(currentUrlRef.current);
      }
    };
  }, [filename, userId]);

  const handleDownload = () => {
    if (videoUrl) {
      const a = document.createElement('a');
      a.href = videoUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  if (!videoUrl) {
    return (
      <div className={`bg-gray-100 rounded-lg flex items-center justify-center ${className}`}>
        <span className="text-gray-500">Loading...</span>
      </div>
    );
  }

  if (type === 'video') {
    return (
      <div className="relative">
        <FrameByFramePlayer
          src={videoUrl}
          className={className}
          fps={fps}
          frameCount={frameCount}
        />
        <button
          onClick={handleDownload}
          className="absolute top-2 right-2 p-1 bg-black/50 hover:bg-black/70 text-white rounded-md transition-colors"
          title={`Download ${filename}`}
        >
          <Download size={16} />
        </button>
      </div>
    );
  } else {
    return (
      <div className="relative aspect-video bg-gray-100 rounded-lg overflow-hidden">
        <Image
          src={videoUrl}
          alt={filename}
          fill
          className="object-contain"
        />
        <button
          onClick={handleDownload}
          className="absolute top-2 right-2 p-1 bg-black/50 hover:bg-black/70 text-white rounded-md transition-colors"
          title={`Download ${filename}`}
        >
          <Download size={16} />
        </button>
      </div>
    );
  }
}

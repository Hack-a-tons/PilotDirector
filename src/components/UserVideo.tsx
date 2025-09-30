import { useUser } from "@/contexts/UserContext";
import { FrameByFramePlayer } from "./FrameByFramePlayer";
import Image from "next/image";
import { useEffect, useState } from "react";

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
          setVideoUrl(url);
        }
      } catch (error) {
        console.error('Error fetching video:', error);
      }
    };

    fetchVideo();

    // Cleanup blob URL on unmount
    return () => {
      if (videoUrl) {
        URL.revokeObjectURL(videoUrl);
      }
    };
  }, [filename, userId]);

  if (!videoUrl) {
    return (
      <div className={`bg-gray-100 rounded-lg flex items-center justify-center ${className}`}>
        <span className="text-gray-500">Loading...</span>
      </div>
    );
  }

  if (type === 'video') {
    return (
      <FrameByFramePlayer
        src={videoUrl}
        className={className}
        fps={fps}
        frameCount={frameCount}
      />
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
      </div>
    );
  }
}

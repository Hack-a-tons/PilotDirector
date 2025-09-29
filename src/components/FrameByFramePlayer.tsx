import React, { useRef, useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react';

interface FrameByFramePlayerProps {
  src: string;
  className?: string;
  fps?: number;
  frameCount?: number;
}

export const FrameByFramePlayer: React.FC<FrameByFramePlayerProps> = ({ 
  src, 
  className, 
  fps: propFps, 
  frameCount: propFrameCount 
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [totalFrames, setTotalFrames] = useState(0);
  const [fps, setFps] = useState(30); // Default FPS
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleLoadedMetadata = () => {
      const duration = video.duration;
      // Use provided FPS or default to 30
      const actualFps = propFps || 30;
      const actualFrameCount = propFrameCount || Math.ceil(duration * actualFps);
      
      setFps(actualFps);
      setTotalFrames(actualFrameCount);
    };

    const handleTimeUpdate = () => {
      const currentTime = video.currentTime;
      // Start counting from frame 1 (like most video editors)
      const frameNumber = Math.floor(currentTime * fps) + 1;
      setCurrentFrame(frameNumber);
    };

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);

    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
    };
  }, [fps, propFps, propFrameCount]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only handle keys when hovering over this video player
      if (!isHovered || !videoRef.current) return;
      
      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          stepBackward();
          break;
        case 'ArrowRight':
          e.preventDefault();
          stepForward();
          break;
        case 'ArrowUp':
          e.preventDefault();
          goToFirstFrame();
          break;
        case 'ArrowDown':
          e.preventDefault();
          goToLastFrame();
          break;
        case ' ':
          e.preventDefault();
          togglePlayPause();
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }); // Removed dependency array - effect runs on every render but that's fine for event listeners

  const stepForward = () => {
    const video = videoRef.current;
    if (!video) return;
    
    video.pause();
    const frameTime = 1 / fps;
    const newTime = video.currentTime + frameTime;
    // Allow going to the very end
    if (newTime < video.duration) {
      video.currentTime = newTime;
    } else {
      video.currentTime = video.duration - 0.001; // Last frame
    }
  };

  const stepBackward = () => {
    const video = videoRef.current;
    if (!video) return;
    
    video.pause();
    const frameTime = 1 / fps;
    const newTime = video.currentTime - frameTime;
    // Don't go before the start
    if (newTime > 0) {
      video.currentTime = newTime;
    }
  };

  const goToFirstFrame = () => {
    const video = videoRef.current;
    if (!video) return;
    
    // If already at or very close to the beginning, do nothing (like left arrow)
    if (video.currentTime < 1 / fps) {
      return;
    }
    
    video.pause();
    video.currentTime = 0;
  };

  const goToLastFrame = () => {
    const video = videoRef.current;
    if (!video) return;
    
    video.pause();
    // Go to the very end, then step back slightly to ensure we're on the last frame
    video.currentTime = video.duration - 0.001;
  };

  const togglePlayPause = () => {
    const video = videoRef.current;
    if (!video) return;
    
    if (isPlaying) {
      video.pause();
    } else {
      video.play();
    }
  };

  return (
    <div 
      ref={containerRef}
      className={className}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <video
        ref={videoRef}
        autoPlay
        muted
        loop
        controls
        className="w-full h-48 rounded bg-gray-200"
      >
        <source src={src} />
        Your browser does not support the video tag.
      </video>
      
      {/* Frame-by-frame controls */}
      <div className={`mt-2 flex items-center justify-between p-2 rounded transition-colors ${
        isHovered ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50'
      }`}>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={stepBackward}
            title="Previous frame (← when focused)"
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          
          <Button
            size="sm"
            variant="outline"
            onClick={togglePlayPause}
            title="Play/Pause (Space when focused)"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </Button>
          
          <Button
            size="sm"
            variant="outline"
            onClick={stepForward}
            title="Next frame (→ when focused)"
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
        
        <div className="text-sm text-gray-600">
          Frame: {currentFrame} / {totalFrames}
          {isHovered && <span className="ml-2 text-blue-600">• Focus</span>}
        </div>
      </div>
    </div>
  );
};

import React from "react";
import type { Item, VideoData } from "@/lib/canvas/types";

interface CardRendererProps {
  item: Item;
  onUpdate?: (id: string, updates: Partial<Item>) => void;
}

export default function CardRenderer({ item, onUpdate }: CardRendererProps) {
  const videoData = item.data as VideoData;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
      <div className="mb-3">
        <h3 className="font-semibold text-gray-900">{item.name}</h3>
        {item.subtitle && (
          <p className="text-sm text-gray-600 mt-1">{item.subtitle}</p>
        )}
      </div>
      
      <div className="space-y-2">
        <div className="text-sm">
          <span className="font-medium">File:</span> {videoData.filename}
        </div>
        
        {videoData.duration && (
          <div className="text-sm">
            <span className="font-medium">Duration:</span> {videoData.duration.toFixed(2)}s
          </div>
        )}
        
        {videoData.width && videoData.height && (
          <div className="text-sm">
            <span className="font-medium">Resolution:</span> {videoData.width}x{videoData.height}
          </div>
        )}
        
        {videoData.size && (
          <div className="text-sm">
            <span className="font-medium">Size:</span> {(videoData.size / 1024 / 1024).toFixed(2)} MB
          </div>
        )}
        
        {videoData.filepath && (
          <div className="mt-3">
            <video 
              controls 
              className="w-full max-h-48 rounded border"
              src={`/videos/${videoData.filename}`}
            >
              Your browser does not support the video tag.
            </video>
          </div>
        )}
      </div>
    </div>
  );
}

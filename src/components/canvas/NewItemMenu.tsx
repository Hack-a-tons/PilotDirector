import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Upload } from "lucide-react";

interface NewItemMenuProps {
  onCreateVideo: (name: string) => void;
}

export default function NewItemMenu({ onCreateVideo }: NewItemMenuProps) {
  const [isCreating, setIsCreating] = useState(false);
  const [videoName, setVideoName] = useState("");

  const handleCreate = () => {
    if (videoName.trim()) {
      onCreateVideo(videoName.trim());
      setVideoName("");
      setIsCreating(false);
    }
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const name = file.name.replace(/\.[^/.]+$/, ""); // Remove extension
      onCreateVideo(name);
    }
  };

  if (isCreating) {
    return (
      <div className="flex items-center space-x-2 p-4 bg-white border border-gray-200 rounded-lg">
        <Input
          value={videoName}
          onChange={(e) => setVideoName(e.target.value)}
          placeholder="Enter video name..."
          onKeyDown={(e) => {
            if (e.key === "Enter") handleCreate();
            if (e.key === "Escape") setIsCreating(false);
          }}
          autoFocus
        />
        <Button onClick={handleCreate} disabled={!videoName.trim()}>
          Create
        </Button>
        <Button variant="outline" onClick={() => setIsCreating(false)}>
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-2">
      <Button onClick={() => setIsCreating(true)}>
        <Plus className="h-4 w-4 mr-2" />
        New Video
      </Button>
      
      <div className="relative">
        <input
          type="file"
          accept="video/*"
          onChange={handleFileUpload}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        <Button variant="outline">
          <Upload className="h-4 w-4 mr-2" />
          Upload Video
        </Button>
      </div>
    </div>
  );
}

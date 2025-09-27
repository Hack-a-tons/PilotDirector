"use client";

import { useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import CardRenderer from "@/components/canvas/CardRenderer";
import { EmptyState } from "@/components/empty-state";
import type { AgentState, Item, VideoData } from "@/lib/canvas/types";
import { initialState, isNonEmptyAgentState, defaultDataFor } from "@/lib/canvas/state";

export default function PilotDirectorPage() {
  const { state, setState } = useCoAgent<AgentState>({
    name: "sample_agent",
    initialState,
  });

  const cachedStateRef = useRef<AgentState>(state ?? initialState);
  useEffect(() => {
    if (isNonEmptyAgentState(state)) {
      cachedStateRef.current = state as AgentState;
    }
  }, [state]);

  const viewState: AgentState = isNonEmptyAgentState(state) ? (state as AgentState) : cachedStateRef.current;
  const [showJsonView, setShowJsonView] = useState<boolean>(false);
  const [files, setFiles] = useState<any[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);

  const fetchFiles = async () => {
    try {
      setLoadingFiles(true);
      const response = await fetch('/api/files');
      const data = await response.json();
      setFiles(data);
    } catch (error) {
      console.error('Error fetching files:', error);
    } finally {
      setLoadingFiles(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  useEffect(() => {
    // Auto-play all videos after files load
    const videos = document.querySelectorAll('video');
    videos.forEach(video => {
      video.muted = true;
      video.play().catch(() => {
        // Autoplay blocked, that's fine
      });
    });
  }, [files]);

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

  // Frontend actions for video management
  useCopilotAction({
    name: "createVideo",
    description: "Create a new video item",
    parameters: [
      { name: "name", type: "string", required: true, description: "Video name/title" },
    ],
    handler: async ({ name }: { name: string }) => {
      const newItem: Item = {
        id: `video-${Date.now()}`,
        type: "video",
        name: name,
        subtitle: "Video file",
        data: defaultDataFor("video"),
      };

      setState((prevState) => ({
        ...prevState,
        items: [...(prevState?.items || []), newItem],
        itemsCreated: (prevState?.itemsCreated || 0) + 1,
        lastAction: `Created video: ${name}`,
      }));

      return `Created video: ${name}`;
    },
  });

  useCopilotAction({
    name: "deleteVideo",
    description: "Delete a video item",
    parameters: [
      { name: "itemId", type: "string", required: true, description: "Video item ID" },
    ],
    handler: async ({ itemId }: { itemId: string }) => {
      setState((prevState) => ({
        ...prevState,
        items: (prevState?.items || []).filter(item => item.id !== itemId),
        lastAction: `Deleted video: ${itemId}`,
      }));

      return `Deleted video: ${itemId}`;
    },
  });

  useCopilotAction({
    name: "setVideoName",
    description: "Set video name/title",
    parameters: [
      { name: "itemId", type: "string", required: true, description: "Video item ID" },
      { name: "name", type: "string", required: true, description: "New video name" },
    ],
    handler: async ({ itemId, name }: { itemId: string; name: string }) => {
      setState((prevState) => ({
        ...prevState,
        items: (prevState?.items || []).map(item =>
          item.id === itemId ? { ...item, name } : item
        ),
        lastAction: `Set video name: ${name}`,
      }));

      return `Set video name: ${name}`;
    },
  });

  useCopilotAction({
    name: "setGlobalTitle",
    description: "Set the global title",
    parameters: [
      { name: "title", type: "string", required: true, description: "Global title" },
    ],
    handler: async ({ title }: { title: string }) => {
      setState((prevState) => ({
        ...prevState,
        globalTitle: title,
        lastAction: `Set global title: ${title}`,
      }));

      return `Set global title: ${title}`;
    },
  });

  useCopilotAction({
    name: "setGlobalDescription",
    description: "Set the global description",
    parameters: [
      { name: "description", type: "string", required: true, description: "Global description" },
    ],
    handler: async ({ description }: { description: string }) => {
      setState((prevState) => ({
        ...prevState,
        globalDescription: description,
        lastAction: `Set global description: ${description}`,
      }));

      return `Set global description: ${description}`;
    },
  });

  const handleItemUpdate = useCallback((id: string, updates: Partial<Item>) => {
    setState((prevState) => ({
      ...prevState,
      items: (prevState?.items || []).map(item =>
        item.id === id ? { ...item, ...updates } : item
      ),
    }));
  }, [setState]);

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {viewState.globalTitle || "PilotDirector"}
              </h1>
              <p className="text-gray-600">
                {viewState.globalDescription || "AI-powered video editing with natural language commands"}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => setShowJsonView(!showJsonView)}
            >
              {showJsonView ? "Files View" : "JSON View"}
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {showJsonView ? (
            <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
              {JSON.stringify(viewState, null, 2)}
            </pre>
          ) : (
            <div>
              {loadingFiles ? (
                <div className="text-center text-gray-500 py-8">Loading files...</div>
              ) : files.length === 0 ? (
                <div className="text-center text-gray-500 py-8">No files found</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {files.map((file) => (
                    <div key={file.name} className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                      {/* Preview/Player */}
                      <div className="mb-3">
                        {file.type === 'video' ? (
                          <video
                            autoPlay
                            muted
                            loop
                            controls
                            className="w-full h-48 rounded bg-gray-200"
                          >
                            <source src={`/api/videos/${file.name}`} />
                            Your browser does not support the video tag.
                          </video>
                        ) : (
                          <img
                            src={`/api/videos/${file.name}`}
                            alt={file.name}
                            className="w-full h-48 object-cover rounded bg-gray-200"
                            onError={(e) => {
                              console.error('Failed to load image:', file.name);
                              const target = e.target as HTMLImageElement;
                              target.style.backgroundColor = '#f3f4f6';
                              target.alt = `Failed to load ${file.name}`;
                            }}
                          />
                        )}
                      </div>

                      {/* File Info */}
                      <div className="space-y-1">
                        <h3 className="font-semibold text-gray-900 truncate" title={file.name}>
                          {file.name}
                        </h3>
                        
                        <div className="text-sm text-gray-600 space-y-0.5">
                          {file.width && file.height && (
                            <div>Resolution: {file.width}×{file.height}</div>
                          )}
                          
                          {file.type === 'video' && file.duration && (
                            <div>Duration: {formatDuration(file.duration)}</div>
                          )}
                          
                          <div>Size: {formatSize(file.size)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Chat Sidebar */}
      <div className="w-96 border-l border-gray-200 bg-white flex flex-col">
        <CopilotChat
          labels={{
            title: "PilotDirector Assistant",
            initial: "Hello! I'm your video editing assistant. Upload videos and give me commands like 'cut first 3 seconds from video1.mp4' or 'concatenate all videos'.",
          }}
        />
      </div>
    </div>
  );
}

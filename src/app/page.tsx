"use client";

import { useCoAgent, useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { RefreshCw, Upload, LogIn, LogOut, User } from "lucide-react";
import Image from "next/image";
import { UserVideo } from "@/components/UserVideo";
import type { AgentState, Item } from "@/lib/canvas/types";
import { initialState, isNonEmptyAgentState, defaultDataFor } from "@/lib/canvas/state";
import { UserProvider, useUser } from "@/contexts/UserContext";

interface FileItem {
  name: string;
  type: 'video' | 'image';
  size: number;
  modified: string;
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  frameCount?: number;
}

function PilotDirectorPage() {
  const { user, userId, loading, signInWithGoogle, signInWithApple, logout } = useUser();
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
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    for (const file of Array.from(files)) {
      try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/upload', {
          method: 'POST',
          headers: {
            'x-user-id': userId
          },
          body: formData
        });

        if (response.ok) {
          console.log(`Uploaded: ${file.name}`);
        } else {
          console.error(`Failed to upload: ${file.name}`);
        }
      } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
      }
    }

    // Refresh file list after upload
    await fetchFiles();
    
    // Clear the input
    event.target.value = '';
  };

  const fetchFiles = async () => {
    try {
      setLoadingFiles(true);
      const response = await fetch('/api/user-files', {
        headers: {
          'x-user-id': userId
        }
      });
      const data = await response.json();
      setFiles(data.files || []);
    } catch (error) {
      console.error('Error fetching files:', error);
    } finally {
      setLoadingFiles(false);
    }
  };

  useEffect(() => {
    if (!loading) {
      fetchFiles();
    }
  }, [loading, userId]);

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

  useCopilotAction({
    name: "refreshFiles",
    description: "Refresh the file display when user requests refresh",
    parameters: [],
    handler: async () => {
      console.log("[DEBUG] refreshFiles action called by AI");
      await fetchFiles();
      return "File display refreshed successfully";
    },
  });

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
        globalTitle: prevState?.globalTitle || "PilotDirector",
        globalDescription: prevState?.globalDescription || "AI Video Editor",
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
        globalTitle: prevState?.globalTitle || "PilotDirector",
        globalDescription: prevState?.globalDescription || "AI Video Editor",
        items: (prevState?.items || []).filter(item => item.id !== itemId),
        itemsCreated: prevState?.itemsCreated || 0,
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
        globalTitle: prevState?.globalTitle || "PilotDirector",
        globalDescription: prevState?.globalDescription || "AI Video Editor",
        items: (prevState?.items || []).map(item =>
          item.id === itemId ? { ...item, name } : item
        ),
        itemsCreated: prevState?.itemsCreated || 0,
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
        globalTitle: title,
        globalDescription: prevState?.globalDescription || "AI Video Editor",
        items: prevState?.items || [],
        itemsCreated: prevState?.itemsCreated || 0,
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
        globalTitle: prevState?.globalTitle || "PilotDirector",
        globalDescription: description,
        items: prevState?.items || [],
        itemsCreated: prevState?.itemsCreated || 0,
        lastAction: `Set global description: ${description}`,
      }));

      return `Set global description: ${description}`;
    },
  });

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
            
            {/* Auth & Upload Section */}
            <div className="flex items-center gap-4">
              {/* Auth Status */}
              <div className="flex items-center gap-2">
                {user ? (
                  <>
                    <User className="h-4 w-4" />
                    <span className="text-sm text-gray-600">{user.email}</span>
                    <Button variant="outline" size="sm" onClick={logout}>
                      <LogOut className="h-4 w-4" />
                    </Button>
                  </>
                ) : (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={signInWithGoogle}>
                      <LogIn className="h-4 w-4 mr-1" />
                      Google
                    </Button>
                    <Button variant="outline" size="sm" onClick={signInWithApple}>
                      <LogIn className="h-4 w-4 mr-1" />
                      Apple
                    </Button>
                  </div>
                )}
              </div>
              
              {/* Upload */}
              <div>
                <input
                  type="file"
                  accept="video/*,image/*"
                  onChange={handleFileUpload}
                  className="hidden"
                  id="file-upload"
                  multiple
                />
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => document.getElementById('file-upload')?.click()}
                >
                  <Upload className="h-4 w-4 mr-1" />
                  Upload
                </Button>
              </div>
            </div>
            
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setShowJsonView(!showJsonView)}
              >
                {showJsonView ? "Files View" : "JSON View"}
              </Button>
              <Button
                variant="outline"
                onClick={fetchFiles}
                disabled={loadingFiles}
                size="sm"
              >
                <RefreshCw className={`h-4 w-4 ${loadingFiles ? 'animate-spin' : ''}`} />
              </Button>
            </div>
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
                        <UserVideo
                          filename={file.name}
                          type={file.type}
                          fps={file.fps}
                          frameCount={file.frameCount}
                          className="w-full"
                        />
                      </div>

                      {/* File Info */}
                      <div className="space-y-1">
                        <h3 className="font-semibold text-gray-900 truncate" title={file.name}>
                          {file.name}
                        </h3>
                        
                        <div className="text-sm text-gray-600">
                          {/* Compact single line: Resolution | Duration/Info | Size */}
                          {file.width && file.height && (
                            <span>{file.width}×{file.height}</span>
                          )}
                          
                          {file.type === 'video' && file.duration && (
                            <>
                              {file.width && file.height && <span>&nbsp;|&nbsp;</span>}
                              <span>
                                {formatDuration(file.duration)}
                                {file.fps && file.frameCount ? (
                                  <span> {file.frameCount}f @{file.fps}fps</span>
                                ) : (
                                  <span> {Math.ceil(file.duration * 30)}f @~30fps</span>
                                )}
                              </span>
                            </>
                          )}
                          
                          <span>&nbsp;|&nbsp;</span>
                          <span>{formatSize(file.size)}</span>
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
      <div className="w-96 border-l border-gray-200 bg-white">
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

export default function Page() {
  return (
    <UserProvider>
      <PilotDirectorPage />
    </UserProvider>
  );
}

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
              {showJsonView ? "Canvas View" : "JSON View"}
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
              {viewState.items.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {viewState.items.map((item) => (
                    <CardRenderer
                      key={item.id}
                      item={item}
                      onUpdate={handleItemUpdate}
                    />
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

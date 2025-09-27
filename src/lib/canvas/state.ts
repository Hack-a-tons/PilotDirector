import { AgentState, CardType, VideoData, ItemData } from "@/lib/canvas/types";

export const initialState: AgentState = {
  items: [],
  globalTitle: "PilotDirector",
  globalDescription: "AI-powered video editing with natural language commands",
  lastAction: "",
  itemsCreated: 0,
};

export function isNonEmptyAgentState(value: unknown): value is AgentState {
  if (value == null || typeof value !== "object") return false;
  const keys = Object.keys(value as Record<string, unknown>);
  return keys.length > 0;
}

export function defaultDataFor(type: CardType): ItemData {
  switch (type) {
    case "video":
      return {
        filename: "",
        filepath: "",
        uploadedAt: new Date().toISOString(),
      } as VideoData;
    default:
      return {
        filename: "",
        filepath: "",
        uploadedAt: new Date().toISOString(),
      } as VideoData;
  }
}





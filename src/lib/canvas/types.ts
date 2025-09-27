export type CardType = "video";

export interface VideoData {
  filename: string;
  filepath: string;
  duration?: number;
  width?: number;
  height?: number;
  size?: number;
  uploadedAt: string;
}

export type ItemData = VideoData;

export interface Item {
  id: string;
  type: CardType;
  name: string; // editable title
  subtitle: string; // subtitle shown under the title
  data: ItemData;
}

export interface AgentState {
  items: Item[];
  globalTitle: string;
  globalDescription: string;
  lastAction?: string;
  itemsCreated: number;
}





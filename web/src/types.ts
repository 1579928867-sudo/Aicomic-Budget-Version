export interface Novel {
  id: number; title: string; author: string; created_at: string;
}

export interface Chapter {
  id: number; novel_id: number; chapter_num: number; status: string; created_at: string;
}

export interface Outfit {
  id: number; tag: string; prompt: string; image_path: string; is_default: number;
}

export interface Character {
  id: number; name: string; status: string; outfits: Outfit[];
}

export interface Scene {
  id: number; name: string; description: string; lighting: string;
  style: string; multi_view_image: string; status: string;
}

export interface Script {
  id: number; raw_json: any; status: string;
}

export interface Shot {
  id: number; shot_num: number; narration: string; dialogue: string;
  camera_movement: string; duration_sec: number; image_prompt: string; status: string;
}

export interface VideoClip {
  id: number; file_path: string; duration_sec: number; shot_num: number; status: string;
}

export interface FinalVideo {
  id: number; file_path: string; file_size: number; created_at: string;
}

export interface Task {
  id: string; type: string; chapter_id: number | null; status: string;
  progress: number; params: string; error?: string; created_at: string;
}

export interface ChatMessage {
  id: number; chapter_id: number | null; role: string; content: string; created_at: string;
}

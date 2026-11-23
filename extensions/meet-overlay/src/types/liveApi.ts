/** Live FastAPI response shapes (localhost only). */

export type LiveTranscriptSegment = {
  id: string;
  text: string;
  start_seconds: number;
  end_seconds: number;
  is_final: boolean;
  speaker?: string;
  words?: Array<{ text: string; start: number; end: number }>;
};

export type LiveResearchResult = {
  model_id: string;
  research_target: string;
  status: string;
  label: string | null;
  evidence: string;
  raw_score: number | null;
  is_cheating_probability: boolean;
};

export type LiveSessionPayload = {
  session_id: string;
  status: string;
  stt_status: string;
  stt_message: string | null;
  stt_name?: string | null;
  sample_rate?: number;
  session_audio_seconds?: number;
  next_expected_sequence?: number;
  transcript_segments: LiveTranscriptSegment[];
  audio_feature_summary?: Record<string, unknown>;
  quality_warnings?: Array<{ id: string; code: string; message: string }>;
  audio_research?: LiveResearchResult;
  transcript_research?: LiveResearchResult;
  detection?: {
    status: string;
    message: string;
    confidence_status: string;
  };
  error_code?: string | null;
  error_message?: string | null;
  backend?: { connected: boolean };
};

export type LiveApiResult =
  | { ok: true; live: LiveSessionPayload }
  | { ok: false; error: { code: string; message: string }; live?: LiveSessionPayload };

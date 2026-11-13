/**
 * Offscreen document: tab audio capture, playback bridge, and PCM chunking.
 *
 * - Audio only (no camera / screen video tracks retained).
 * - Does not write audio to disk.
 * - Posts bounded PCM chunks to the service worker (localhost upload happens there).
 */

import {
  DEFAULT_CHUNK_FRAMES,
  downmixToMono,
  encodePcmChunkBase64,
} from "../live/pcmEncode";
import { MessageType, type ExtensionMessage } from "../types/messages";

type ActiveCapture = {
  tabId: number;
  stream: MediaStream;
  audioContext: AudioContext;
  sourceNode: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode | null;
  silentGain: GainNode | null;
  audioEl: HTMLAudioElement | null;
  pending: Float32Array[];
  pendingFrames: number;
  sequence: number;
  startedAtMs: number;
  sending: boolean;
};

let active: ActiveCapture | null = null;

function isPermissionError(err: unknown): boolean {
  const name = err instanceof DOMException ? err.name : "";
  const msg = err instanceof Error ? err.message : String(err);
  return (
    name === "NotAllowedError" ||
    name === "PermissionDeniedError" ||
    /permission|denied|not allowed/i.test(msg)
  );
}

function flushChunk(force = false): void {
  const current = active;
  if (!current || current.sending) return;
  if (!force && current.pendingFrames < DEFAULT_CHUNK_FRAMES) return;
  if (current.pendingFrames <= 0) return;

  const merged = new Float32Array(current.pendingFrames);
  let offset = 0;
  for (const part of current.pending) {
    merged.set(part, offset);
    offset += part.length;
  }
  current.pending = [];
  current.pendingFrames = 0;

  // Take at most one transport chunk worth; keep remainder for next flush.
  const take = Math.min(merged.length, DEFAULT_CHUNK_FRAMES * 2); // hard bound ~3s
  const chunkSamples = merged.subarray(0, take);
  if (merged.length > take) {
    const rest = merged.subarray(take);
    current.pending.push(rest.slice());
    current.pendingFrames = rest.length;
  }

  try {
    const encoded = encodePcmChunkBase64(chunkSamples, current.audioContext.sampleRate);
    current.sequence += 1;
    const clientRelStartMs = performance.now() - current.startedAtMs;
    current.sending = true;
    chrome.runtime.sendMessage(
      {
        type: MessageType.OFFSCREEN_CHUNK,
        payload: {
          tabId: current.tabId,
          sequence: current.sequence,
          sampleRate: encoded.sampleRate,
          channels: encoded.channels,
          encoding: "pcm_s16le",
          pcmBase64: encoded.pcmBase64,
          durationMs: encoded.durationMs,
          clientRelStartMs,
        },
      } satisfies ExtensionMessage,
      () => {
        void chrome.runtime.lastError;
        if (active === current) {
          current.sending = false;
          // Opportunistic flush if more audio accumulated while waiting.
          flushChunk(false);
        }
      },
    );
  } catch (err) {
    current.sending = false;
    chrome.runtime.sendMessage({
      type: MessageType.OFFSCREEN_FAILED,
      tabId: current.tabId,
      code: "error",
      message: err instanceof Error ? err.message : "PCM chunk encoding failed",
    } satisfies ExtensionMessage);
  }
}

async function stopActive(notify: "stopped" | "interrupted" | "none", detail?: string): Promise<void> {
  const current = active;
  active = null;
  if (!current) return;

  try {
    flushChunk(true);
  } catch {
    /* ignore */
  }

  try {
    current.processor?.disconnect();
  } catch {
    /* ignore */
  }
  try {
    current.silentGain?.disconnect();
  } catch {
    /* ignore */
  }
  try {
    current.sourceNode.disconnect();
  } catch {
    /* already disconnected */
  }
  try {
    await current.audioContext.close();
  } catch {
    /* ignore */
  }
  if (current.audioEl) {
    try {
      current.audioEl.pause();
      current.audioEl.srcObject = null;
    } catch {
      /* ignore */
    }
  }
  for (const track of current.stream.getTracks()) {
    try {
      track.stop();
    } catch {
      /* ignore */
    }
  }

  current.pending = [];
  current.pendingFrames = 0;

  if (notify === "none") return;
  const message: ExtensionMessage = {
    type: MessageType.OFFSCREEN_ENDED,
    tabId: current.tabId,
    reason: notify,
    message: detail,
  };
  chrome.runtime.sendMessage(message).catch(() => {
    /* SW may be restarting */
  });
}

async function startCapture(streamId: string, tabId: number): Promise<void> {
  if (active) {
    chrome.runtime.sendMessage({
      type: MessageType.OFFSCREEN_FAILED,
      tabId,
      code: "error",
      message: "Offscreen capture already holds an active stream.",
    } satisfies ExtensionMessage);
    return;
  }

  try {
    const constraints = {
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    } as unknown as MediaStreamConstraints;

    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    for (const track of stream.getVideoTracks()) {
      track.stop();
      stream.removeTrack(track);
    }

    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) {
      for (const track of stream.getTracks()) track.stop();
      chrome.runtime.sendMessage({
        type: MessageType.OFFSCREEN_FAILED,
        tabId,
        code: "error",
        message: "Tab capture returned no audio track.",
      } satisfies ExtensionMessage);
      return;
    }

    for (const track of audioTracks) {
      track.addEventListener("ended", () => {
        void stopActive("interrupted", "The tab audio track ended.");
      });
    }

    const audioContext = new AudioContext();
    const sourceNode = audioContext.createMediaStreamSource(stream);
    // Preserve remote Meet playback.
    sourceNode.connect(audioContext.destination);
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }

    let audioEl: HTMLAudioElement | null = null;
    try {
      audioEl = new Audio();
      audioEl.srcObject = stream;
      audioEl.autoplay = true;
      await audioEl.play();
    } catch {
      audioEl = null;
    }

    // Tap for PCM chunking without adding audible gain.
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    sourceNode.connect(processor);
    processor.connect(silentGain);
    silentGain.connect(audioContext.destination);

    const session: ActiveCapture = {
      tabId,
      stream,
      audioContext,
      sourceNode,
      processor,
      silentGain,
      audioEl,
      pending: [],
      pendingFrames: 0,
      sequence: 0,
      startedAtMs: performance.now(),
      sending: false,
    };
    active = session;

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      if (active !== session) return;
      const input = event.inputBuffer;
      const channelData = input.getChannelData(0);
      // Copy — the buffer is reused by the audio system.
      const copy = new Float32Array(channelData.length);
      copy.set(channelData);
      const mono = input.numberOfChannels > 1 ? downmixToMono(copy, input.numberOfChannels) : copy;
      session.pending.push(mono);
      session.pendingFrames += mono.length;
      flushChunk(false);
    };

    chrome.runtime.sendMessage({
      type: MessageType.OFFSCREEN_STARTED,
      tabId,
    } satisfies ExtensionMessage);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to start tab audio capture";
    chrome.runtime.sendMessage({
      type: MessageType.OFFSCREEN_FAILED,
      tabId,
      code: isPermissionError(err) ? "permission_denied" : "error",
      message,
    } satisfies ExtensionMessage);
  }
}

chrome.runtime.onMessage.addListener((message: ExtensionMessage) => {
  if (!message || typeof message !== "object" || !("type" in message)) {
    return;
  }

  if (message.type === MessageType.OFFSCREEN_START) {
    void startCapture(message.streamId, message.tabId);
    return;
  }

  if (message.type === MessageType.OFFSCREEN_STOP) {
    void stopActive("stopped", "Live audio capture stopped by the interviewer.");
  }
});

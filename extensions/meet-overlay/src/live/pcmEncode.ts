/**
 * Browser-native PCM helpers for live Meet tab audio chunks.
 * No external codec libraries.
 */

export const TARGET_SAMPLE_RATE = 16_000;
export const TARGET_CHANNELS = 1;
/** ~1.5 s of 16 kHz mono s16le */
export const DEFAULT_CHUNK_FRAMES = Math.floor(TARGET_SAMPLE_RATE * 1.5);
export const MAX_CHUNK_BYTES = 256 * 1024;

/** Clamp float sample to [-1, 1] then convert to int16 without soft clipping bias. */
export function floatToInt16Sample(sample: number): number {
  const x = Math.max(-1, Math.min(1, sample));
  return x < 0 ? Math.round(x * 0x8000) : Math.round(x * 0x7fff);
}

/** Linear resample mono Float32Array from sourceRate → targetRate. */
export function resampleMonoLinear(
  input: Float32Array,
  sourceRate: number,
  targetRate: number = TARGET_SAMPLE_RATE,
): Float32Array {
  if (sourceRate <= 0 || targetRate <= 0) {
    return new Float32Array(0);
  }
  if (sourceRate === targetRate) {
    return input.slice();
  }
  const outLength = Math.max(0, Math.round((input.length * targetRate) / sourceRate));
  const output = new Float32Array(outLength);
  if (outLength === 0 || input.length === 0) return output;
  const ratio = sourceRate / targetRate;
  for (let i = 0; i < outLength; i++) {
    const srcPos = i * ratio;
    const i0 = Math.floor(srcPos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = srcPos - i0;
    output[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return output;
}

export function floatMonoToPcmS16le(input: Float32Array): ArrayBuffer {
  const out = new ArrayBuffer(input.length * 2);
  const view = new DataView(out);
  for (let i = 0; i < input.length; i++) {
    view.setInt16(i * 2, floatToInt16Sample(input[i]), true);
  }
  return out;
}

export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export function encodePcmChunkBase64(
  floatMono: Float32Array,
  sourceRate: number,
): {
  pcmBase64: string;
  sampleRate: number;
  channels: number;
  durationMs: number;
  byteLength: number;
} {
  const resampled = resampleMonoLinear(floatMono, sourceRate, TARGET_SAMPLE_RATE);
  const pcm = floatMonoToPcmS16le(resampled);
  if (pcm.byteLength > MAX_CHUNK_BYTES) {
    throw new Error(`PCM chunk exceeds max size (${pcm.byteLength} > ${MAX_CHUNK_BYTES})`);
  }
  return {
    pcmBase64: arrayBufferToBase64(pcm),
    sampleRate: TARGET_SAMPLE_RATE,
    channels: TARGET_CHANNELS,
    durationMs: (resampled.length / TARGET_SAMPLE_RATE) * 1000,
    byteLength: pcm.byteLength,
  };
}

/** Downmix interleaved multi-channel Float32 to mono. */
export function downmixToMono(input: Float32Array, channels: number): Float32Array {
  if (channels <= 1) return input;
  const frames = Math.floor(input.length / channels);
  const out = new Float32Array(frames);
  for (let i = 0; i < frames; i++) {
    let sum = 0;
    for (let c = 0; c < channels; c++) {
      sum += input[i * channels + c];
    }
    out[i] = sum / channels;
  }
  return out;
}

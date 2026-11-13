import { describe, expect, it } from "vitest";
import {
  DEFAULT_CHUNK_FRAMES,
  TARGET_SAMPLE_RATE,
  arrayBufferToBase64,
  downmixToMono,
  encodePcmChunkBase64,
  floatToInt16Sample,
  resampleMonoLinear,
} from "./pcmEncode";

describe("pcmEncode", () => {
  it("clamps float samples into int16 range", () => {
    expect(floatToInt16Sample(0)).toBe(0);
    expect(floatToInt16Sample(1)).toBe(0x7fff);
    expect(floatToInt16Sample(-1)).toBe(-0x8000);
    expect(floatToInt16Sample(2)).toBe(0x7fff);
    expect(floatToInt16Sample(-2)).toBe(-0x8000);
  });

  it("resamples 48 kHz to 16 kHz approximately 3:1", () => {
    const input = new Float32Array(4800);
    for (let i = 0; i < input.length; i++) input[i] = Math.sin(i / 20);
    const out = resampleMonoLinear(input, 48000, 16000);
    expect(out.length).toBe(1600);
  });

  it("identity resample copies samples", () => {
    const input = new Float32Array([0.1, -0.2, 0.3]);
    const out = resampleMonoLinear(input, 16000, 16000);
    expect(out.length).toBe(3);
    expect(out[0]).toBeCloseTo(0.1, 5);
    expect(out[1]).toBeCloseTo(-0.2, 5);
    expect(out[2]).toBeCloseTo(0.3, 5);
  });

  it("downmixes stereo to mono", () => {
    const stereo = new Float32Array([1, -1, 0.5, 0.5]);
    const mono = downmixToMono(stereo, 2);
    expect(mono.length).toBe(2);
    expect(mono[0]).toBeCloseTo(0);
    expect(mono[1]).toBeCloseTo(0.5);
  });

  it("encodes a bounded base64 PCM chunk", () => {
    const frames = DEFAULT_CHUNK_FRAMES;
    const input = new Float32Array(frames);
    input[0] = 0.25;
    const encoded = encodePcmChunkBase64(input, TARGET_SAMPLE_RATE);
    expect(encoded.sampleRate).toBe(16000);
    expect(encoded.channels).toBe(1);
    expect(encoded.byteLength).toBe(frames * 2);
    expect(encoded.pcmBase64.length).toBeGreaterThan(8);
    // Round-trip base64 length sanity.
    expect(atob(encoded.pcmBase64).length).toBe(frames * 2);
    expect(arrayBufferToBase64(new Uint8Array([1, 2, 3]).buffer).length).toBeGreaterThan(0);
  });
});

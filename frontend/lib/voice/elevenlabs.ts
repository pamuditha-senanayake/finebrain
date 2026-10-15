// Server only: the ElevenLabs key lives in ELEVENLABS_API_KEY (frontend/.env.local) and never reaches the browser.
// The browser talks to /api/voice/speak and /api/voice/listen, which call ElevenLabs from here.
import "server-only";

const API = "https://api.elevenlabs.io/v1";

/** George, a calm narrator voice available on every account. Override with ELEVENLABS_VOICE_ID. */
const DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb";

/** Answers are spoken short; anything longer is cut, which also caps the cost of one reply. */
export const MAX_SPOKEN_CHARS = 600;

export class VoiceError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function key(): string {
  const k = process.env.ELEVENLABS_API_KEY;
  if (!k) throw new VoiceError("Voice is not set up: ELEVENLABS_API_KEY is missing.", 503);
  return k;
}

/** Text to MP3 audio. Flash is the low latency model, so the reply starts quickly. */
export async function speak(text: string): Promise<Response> {
  const voice = process.env.ELEVENLABS_VOICE_ID || DEFAULT_VOICE;
  const res = await fetch(`${API}/text-to-speech/${voice}/stream?output_format=mp3_44100_128`, {
    method: "POST",
    headers: { "xi-api-key": key(), "Content-Type": "application/json", Accept: "audio/mpeg" },
    body: JSON.stringify({ text: text.slice(0, MAX_SPOKEN_CHARS), model_id: "eleven_flash_v2_5" }),
  });
  if (!res.ok || !res.body) throw new VoiceError(`ElevenLabs could not speak (${res.status}).`, 502);
  return res;
}

/** Recorded audio to text with Scribe. */
export async function transcribe(audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("model_id", "scribe_v1");
  form.append("file", audio, "speech.webm");
  const res = await fetch(`${API}/speech-to-text`, { method: "POST", headers: { "xi-api-key": key() }, body: form });
  if (!res.ok) throw new VoiceError(`ElevenLabs could not transcribe (${res.status}).`, 502);
  const data = (await res.json()) as { text?: string };
  return (data.text ?? "").trim();
}

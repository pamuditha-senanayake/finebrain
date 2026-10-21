// Server only: the ElevenLabs key lives in ELEVENLABS_API_KEY (frontend/.env.local) and never reaches the browser.
// The browser talks to /api/voice/speak and /api/voice/listen, which call ElevenLabs from here.
import "server-only";

const API = "https://api.elevenlabs.io/v1";

/** George, a calm narrator voice available on every account. Override with ELEVENLABS_VOICE_ID. */
const DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb";

/** Answers are spoken short; anything longer is cut, which also caps the cost of one reply. */
export const MAX_SPOKEN_CHARS = 600;

/** Raw 16-bit mono PCM at 24 kHz: the browser can play each chunk the moment it lands (speaker.ts), unlike MP3. */
export const SPEAK_FORMAT = "pcm_24000";

/** Scribe v2 is the newer, more accurate speech to text model. */
const LISTEN_MODEL = "scribe_v2";

/** Questions are asked in English; naming it stops Scribe guessing a wrong language from a short clip. */
const LISTEN_LANGUAGE = "en";

/** Our own words Scribe would otherwise hear as common ones. Kept under 100 so short clips are not billed as 20 seconds. */
const KEY_TERMS = ["Finebase", "finebrain", "APIT", "EPF", "ETF", "VAT", "Vault", "Commons", "Distiller"];

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

/** Text to raw PCM audio, streamed. Flash is the low latency model, so the reply starts quickly. */
export async function speak(text: string): Promise<Response> {
  const voice = process.env.ELEVENLABS_VOICE_ID || DEFAULT_VOICE;
  const res = await fetch(`${API}/text-to-speech/${voice}/stream?output_format=${SPEAK_FORMAT}`, {
    method: "POST",
    headers: { "xi-api-key": key(), "Content-Type": "application/json", Accept: "audio/pcm" },
    body: JSON.stringify({ text: text.slice(0, MAX_SPOKEN_CHARS), model_id: "eleven_flash_v2_5" }),
  });
  if (!res.ok || !res.body) throw new VoiceError(`ElevenLabs could not speak (${res.status}).`, 502);
  return res;
}

/** Safari records MP4 and Chrome records WebM; the file name tells Scribe which. */
function extensionOf(type: string): string {
  if (type.includes("mp4") || type.includes("aac")) return "m4a";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("ogg")) return "ogg";
  if (type.includes("wav")) return "wav";
  return "webm";
}

/** Recorded audio to text with Scribe. */
export async function transcribe(audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("model_id", LISTEN_MODEL);
  form.append("language_code", LISTEN_LANGUAGE);
  for (const term of KEY_TERMS) form.append("keyterms", term);
  form.append("file", audio, `speech.${extensionOf(audio.type)}`);
  const res = await fetch(`${API}/speech-to-text`, { method: "POST", headers: { "xi-api-key": key() }, body: form });
  if (!res.ok) throw new VoiceError(`ElevenLabs could not transcribe (${res.status}).`, 502);
  const data = (await res.json()) as { text?: string };
  return (data.text ?? "").trim();
}

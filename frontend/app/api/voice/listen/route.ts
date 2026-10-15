import { VoiceError, transcribe } from "@/lib/voice/elevenlabs";

/** About two minutes of compressed speech. Longer recordings are refused. */
const MAX_BYTES = 5 * 1024 * 1024;

/** POST raw recorded audio (the request body) → { text }, transcribed by ElevenLabs Scribe. */
export async function POST(request: Request) {
  const audio = await request.blob();
  if (!audio.size) return Response.json({ error: "No audio received." }, { status: 400 });
  if (audio.size > MAX_BYTES) return Response.json({ error: "The recording is too long." }, { status: 413 });
  try {
    return Response.json({ text: await transcribe(audio) });
  } catch (e) {
    const status = e instanceof VoiceError ? e.status : 500;
    return Response.json({ error: e instanceof Error ? e.message : "Voice failed." }, { status });
  }
}

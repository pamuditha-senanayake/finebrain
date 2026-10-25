import { z } from "zod";
import { MAX_SPOKEN_CHARS, VoiceError, speak } from "@/lib/voice/elevenlabs";

const Body = z.object({ text: z.string().trim().min(1).max(MAX_SPOKEN_CHARS * 2) });

/** POST { text } → raw 16-bit PCM at 24 kHz, spoken by ElevenLabs. Streams, so playback starts with the first chunk. */
export async function POST(request: Request) {
  const parsed = Body.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return Response.json({ error: "Send { text } with something to say." }, { status: 400 });
  try {
    const res = await speak(parsed.data.text);
    return new Response(res.body, { headers: { "Content-Type": "audio/L16; rate=24000; channels=1", "Cache-Control": "no-store" } });
  } catch (e) {
    const status = e instanceof VoiceError ? e.status : 500;
    return Response.json({ error: e instanceof Error ? e.message : "Voice failed." }, { status });
  }
}

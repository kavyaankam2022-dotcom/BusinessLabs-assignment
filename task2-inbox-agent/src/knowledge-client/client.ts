import { z } from 'zod';
import { knowledgeResponseSchema, type KnowledgeResponse } from '../types.js';

const errorSchema = z.object({
  code: z.string().optional(),
  message: z.string().optional(),
  request_id: z.string().optional(),
});

export type KnowledgeLookup =
  | { ok: true; response: KnowledgeResponse }
  | { ok: false; error: string; requestId?: string };

export async function queryKnowledge(
  question: string,
  customerContext: string,
  fetcher: typeof fetch = fetch,
): Promise<KnowledgeLookup> {
  const baseUrl = process.env.KB_API_URL ?? 'http://127.0.0.1:8000';
  const timeoutMs = Number(process.env.INBOX_KB_TIMEOUT_MS ?? 25_000);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.KB_API_KEY) headers['X-API-Key'] = process.env.KB_API_KEY;

  try {
    const response = await fetcher(`${baseUrl.replace(/\/$/, '')}/query`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question, customer_context: customerContext, top_k: 5 }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const parsed = errorSchema.safeParse(body);
      return {
        ok: false,
        error: parsed.success ? parsed.data.message ?? `Knowledge service returned HTTP ${response.status}.` : `Knowledge service returned HTTP ${response.status}.`,
        requestId: parsed.success ? parsed.data.request_id : response.headers.get('X-Request-ID') ?? undefined,
      };
    }
    const parsed = knowledgeResponseSchema.safeParse(body);
    if (!parsed.success) return { ok: false, error: 'Knowledge service returned an invalid response.' };
    return { ok: true, response: parsed.data };
  } catch (error) {
    if (error instanceof Error && error.name === 'TimeoutError') {
      return { ok: false, error: 'Knowledge service request timed out.' };
    }
    return { ok: false, error: 'Knowledge service is unavailable.' };
  }
}

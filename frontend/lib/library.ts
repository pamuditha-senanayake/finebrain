import type { Document, Fact } from "@/contracts";

/** A folder in the Library. New documents are filed into one automatically by their type. */
export type Folder = { id: string; name: string; types: string[] };

export const FOLDERS: Folder[] = [
  { id: "bank", name: "Bank statements", types: ["statement"] },
  { id: "invoices", name: "Invoices and receipts", types: ["invoice", "receipt"] },
  { id: "ledgers", name: "Ledgers and payroll", types: ["ledger", "schedule"] },
  { id: "contracts", name: "Contracts", types: ["contract"] },
  { id: "policies", name: "Policies and legal", types: ["policy", "legal", "handbook"] },
  { id: "pricing", name: "Pricing", types: ["pricing"] },
  { id: "registers", name: "Certificates and registers", types: ["certificate", "register"] },
  { id: "evidence", name: "Evidence", types: ["evidence"] },
  { id: "reports", name: "Reports and exports", types: ["report", "release", "export", "monitor", "presentation"] },
  { id: "other", name: "Other", types: [] },
];

const BY_TYPE = new Map(FOLDERS.flatMap((f) => f.types.map((t) => [t, f] as const)));

export function folderOf(doc: Pick<Document, "type">): Folder {
  return BY_TYPE.get(doc.type) ?? FOLDERS[FOLDERS.length - 1];
}

/** Words people use for the same thing, so a search finds documents by meaning, not only by name. */
const RELATED: Record<string, string[]> = {
  bank: ["statement"],
  money: ["statement", "invoice", "ledger", "receipt"],
  receipt: ["receipt", "invoice", "order"],
  bill: ["invoice"],
  salary: ["payroll", "epf", "apit"],
  wages: ["payroll", "epf"],
  staff: ["payroll", "epf", "handbook"],
  tax: ["vat", "apit", "epf"],
  price: ["pricing", "rate"],
  cost: ["pricing", "rate", "invoice"],
  agreement: ["contract", "msa"],
  client: ["contract", "msa", "customer"],
  customer: ["receipt", "order", "nps", "cus"],
  refund: ["refund", "policy"],
  rules: ["policy", "handbook", "terms"],
  privacy: ["privacy", "personal"],
  legal: ["terms", "privacy", "legal"],
  owner: ["shareholder", "register"],
  outage: ["incident", "rca"],
  problem: ["incident", "rca"],
  update: ["release"],
};

export type DocHit = { doc: Document; score: number; reason: string | null };

/**
 * Search by name and by meaning: matches the title and folder, related words,
 * and what the document says (the facts the brain extracted from it).
 */
export function searchDocuments(docs: Document[], factsByDoc: Map<string, Fact[]>, query: string): DocHit[] {
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  if (words.length === 0) return docs.map((doc) => ({ doc, score: 0, reason: null }));
  const hits: DocHit[] = [];
  for (const doc of docs) {
    const title = `${doc.title} ${doc.type}`.toLowerCase();
    const name = `${title} ${folderOf(doc).name}`.toLowerCase();
    const facts = factsByDoc.get(doc.id) ?? [];
    let score = 0;
    let reason: string | null = null;
    for (const w of words) {
      if (name.includes(w)) score += 3;
      // Related words match the document itself, not its folder, so a shared folder does not drag in strangers.
      else if ((RELATED[w] ?? []).some((r) => title.includes(r))) score += 2;
      const said = facts.find((f) => f.statement.toLowerCase().includes(w) || f.evidence.some((e) => e.quote.toLowerCase().includes(w)));
      if (said) {
        score += 1;
        reason ??= said.statement;
      }
    }
    if (score > 0) hits.push({ doc, score, reason });
  }
  return hits.sort((a, b) => b.score - a.score);
}

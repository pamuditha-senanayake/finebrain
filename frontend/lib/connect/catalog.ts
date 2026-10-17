import { BriefcaseBusiness, Code2, CreditCard, Database, FileText, Globe, Mail, MessageSquare, Plug, Upload, Webhook, type LucideIcon } from "lucide-react";

/**
 * How the brain gets at a system's data.
 * oauth: the person signs in and grants read access. database: a read-only connection string.
 * mcp: the system already has an MCP server, so the brain reads through it.
 * website: the brain reads public pages. upload: exported files. webhook: the system pushes events to a URL.
 */
export type Method = "oauth" | "database" | "mcp" | "website" | "upload" | "webhook";

export type Category = "email" | "chat" | "code" | "docs" | "sales" | "money" | "data" | "other";

export type Connector = { id: string; name: string; category: Category; method: Method };

export const CATEGORY: Record<Category, { label: string; icon: LucideIcon }> = {
  email: { label: "Email and calendar", icon: Mail },
  chat: { label: "Chat", icon: MessageSquare },
  code: { label: "Code and work", icon: Code2 },
  docs: { label: "Docs", icon: FileText },
  sales: { label: "Customers", icon: BriefcaseBusiness },
  money: { label: "Money", icon: CreditCard },
  data: { label: "Databases", icon: Database },
  other: { label: "Anything else", icon: Plug },
};

export const METHOD: Record<Method, { label: string; icon: LucideIcon }> = {
  oauth: { label: "Sign in", icon: Plug },
  database: { label: "Read-only link", icon: Database },
  mcp: { label: "MCP server", icon: Plug },
  website: { label: "Read the site", icon: Globe },
  upload: { label: "Upload files", icon: Upload },
  webhook: { label: "Webhook", icon: Webhook },
};

export const CONNECTORS: Connector[] = [
  { id: "gmail", name: "Gmail", category: "email", method: "oauth" },
  { id: "outlook", name: "Outlook", category: "email", method: "oauth" },
  { id: "gcal", name: "Google Calendar", category: "email", method: "oauth" },
  { id: "slack", name: "Slack", category: "chat", method: "oauth" },
  { id: "teams", name: "Microsoft Teams", category: "chat", method: "oauth" },
  { id: "whatsapp", name: "WhatsApp Business", category: "chat", method: "oauth" },
  { id: "github", name: "GitHub", category: "code", method: "oauth" },
  { id: "gitlab", name: "GitLab", category: "code", method: "oauth" },
  { id: "jira", name: "Jira", category: "code", method: "oauth" },
  { id: "linear", name: "Linear", category: "code", method: "oauth" },
  { id: "notion", name: "Notion", category: "docs", method: "oauth" },
  { id: "gdrive", name: "Google Drive", category: "docs", method: "oauth" },
  { id: "confluence", name: "Confluence", category: "docs", method: "oauth" },
  { id: "sharepoint", name: "SharePoint", category: "docs", method: "oauth" },
  { id: "hubspot", name: "HubSpot", category: "sales", method: "oauth" },
  { id: "salesforce", name: "Salesforce", category: "sales", method: "oauth" },
  { id: "zendesk", name: "Zendesk", category: "sales", method: "oauth" },
  { id: "intercom", name: "Intercom", category: "sales", method: "oauth" },
  { id: "stripe", name: "Stripe", category: "money", method: "oauth" },
  { id: "shopify", name: "Shopify", category: "money", method: "oauth" },
  { id: "quickbooks", name: "QuickBooks", category: "money", method: "oauth" },
  { id: "xero", name: "Xero", category: "money", method: "oauth" },
  { id: "postgres", name: "PostgreSQL", category: "data", method: "database" },
  { id: "mysql", name: "MySQL", category: "data", method: "database" },
  { id: "sqlserver", name: "SQL Server", category: "data", method: "database" },
  { id: "mongodb", name: "MongoDB", category: "data", method: "database" },
  { id: "bigquery", name: "BigQuery", category: "data", method: "database" },
  { id: "snowflake", name: "Snowflake", category: "data", method: "database" },
  { id: "website", name: "Website", category: "other", method: "website" },
  { id: "mcp", name: "MCP server", category: "other", method: "mcp" },
  { id: "files", name: "Files", category: "other", method: "upload" },
  { id: "webhook", name: "Webhook", category: "other", method: "webhook" },
];

/** What a database link looks like, so the field shows the right shape. */
export const DB_PLACEHOLDER: Record<string, string> = {
  postgres: "postgres://readonly@host:5432/db",
  mysql: "mysql://readonly@host:3306/db",
  sqlserver: "sqlserver://readonly@host:1433;database=db",
  mongodb: "mongodb+srv://readonly@cluster/db",
  bigquery: "bigquery://project/dataset",
  snowflake: "snowflake://readonly@account/db/schema",
};

/**
 * What the brain listens to on each kind of system, asked when connecting,
 * and the kinds of data it then reads. Always read only.
 */
export type Listen = { label: string; placeholder: string; reads: string[] };

const LISTEN: Record<Category, Listen> = {
  email: { label: "Which inboxes?", placeholder: "support@yourcompany.com, sales@yourcompany.com", reads: ["Emails", "Threads", "Attachments"] },
  chat: { label: "Which channels?", placeholder: "#support, #sales", reads: ["Messages", "Threads", "Shared files"] },
  code: { label: "Which repos or projects?", placeholder: "yourcompany/app, yourcompany/api", reads: ["Issues", "Pull requests", "Commits", "Docs"] },
  docs: { label: "Which spaces or folders?", placeholder: "Handbook, Policies", reads: ["Pages", "Files", "Comments"] },
  sales: { label: "Which account?", placeholder: "yourcompany.hubspot.com", reads: ["Contacts", "Deals", "Tickets"] },
  money: { label: "Which account?", placeholder: "Store or account name", reads: ["Payments", "Invoices", "Refunds"] },
  data: { label: "Connection link", placeholder: "", reads: ["Tables you allow", "Row counts", "Schema"] },
  other: { label: "", placeholder: "", reads: [] },
};

const LISTEN_BY_ID: Record<string, Listen> = {
  gcal: { label: "Which calendars?", placeholder: "team@yourcompany.com", reads: ["Events", "Attendees", "Meeting notes"] },
  website: { label: "", placeholder: "", reads: ["Public pages", "Forms", "Pricing and FAQs"] },
  mcp: { label: "", placeholder: "", reads: ["Tools and resources it shares"] },
  files: { label: "", placeholder: "", reads: ["File contents"] },
  webhook: { label: "", placeholder: "", reads: ["Events it sends"] },
  other: { label: "", placeholder: "", reads: ["What its connection shares"] },
};

export const listenOf = (c: Pick<Connector, "id" | "category">): Listen => LISTEN_BY_ID[c.id] ?? LISTEN[c.category];

export const connectorById = (id: string) => CONNECTORS.find((c) => c.id === id);

/**
 * For a tool that is not in the list, the ways the brain can still reach it,
 * in the order worth trying: an MCP server, a webhook, exported files, or asking us to add it.
 */
export const FALLBACKS: { id: Method | "request"; label: string; hint: string }[] = [
  { id: "mcp", label: "It has an MCP server", hint: "Paste its URL" },
  { id: "webhook", label: "It can send webhooks", hint: "We give you a URL" },
  { id: "upload", label: "I can export files", hint: "CSV, PDF, docs" },
  { id: "request", label: "Ask us to add it", hint: "We build the connector" },
];

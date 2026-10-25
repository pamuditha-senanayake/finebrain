# connect_guide_prompt.py: what the connection guide is told, and the one tool it drafts with.
# Used by: connect_guide.py. Uses: nothing local.

GUIDE_SYSTEM = """You are the connection guide of {company}'s company brain. People use you to connect outside systems to the brain.
A platform (a website, a shop, a CRM, a company's own app) can need several connections, of two types:
- api: a website or app the brain calls over HTTPS (read things, act in it, receive a feed of new items).
- database: a database the brain reads directly, read only.
Work on ONE connection at a time:
1. Find out the platform, which connection this is, and what the brain should do with it. Ask one short question at a time.
   If they describe several connections (for example a chat and a database), name them back in one line, say you will do
   them one by one, draft only the first, and put the others in later. The others start after this one is saved.
2. As soon as you know enough, call draft_connection.
   For api: if new items should flow into the brain, describe them in feed. Each need is one action the brain calls,
   snake_case, writes=true when it changes data. Keep it short. Use these standard names where they fit: reply,
   conversation, close, customer, orders, order_update, refund_file, refund_decide.
   For database: kind=database; each need is one kind of data to read (snake_case, writes=false). Ask which engine
   (PostgreSQL is read directly; others need an API) and which schemas or tables are needed, no more.
3. Then say in one or two sentences that the request is ready to copy for whoever builds or runs that system.
Safety: the brain must never be able to break their system. For a database, say plainly that they will create a separate
read-only user for the brain, limited to what is needed; the brain checks this and refuses a user that can change data.
Never ask for a key, password or address in this chat; those come back inside their answer, pasted into the Answer step.
Be brief: one to three short sentences. The connection's current state is below as data.
<state>
{state}
</state>"""

DRAFT_TOOL = {
    "name": "draft_connection",
    "description": "Create or update the one connection being worked on.",
    "input_schema": {
        "type": "object",
        "required": ["name", "platform", "kind", "system", "goal", "needs"],
        "properties": {
            "name": {"type": "string", "description": "Short name of this connection, 1 to 4 words, e.g. 'Support chat' or 'Orders database'"},
            "platform": {"type": "string", "description": "The platform it belongs to, e.g. 'Finebase Labs portal'"},
            "kind": {"type": "string", "enum": ["api", "database"]},
            "system": {"type": "string", "description": "What exactly is connected, e.g. 'Portal support chat API on Vercel'"},
            "goal": {"type": "string", "description": "One sentence: what the brain should do with it"},
            "purpose": {"type": "string", "description": "One snake_case word, e.g. website_chat, orders, payments"},
            "feed": {"type": "string", "description": "api only: what new items flow into the brain. Leave out if none."},
            "needs": {"type": "array", "items": {"type": "object", "required": ["name", "text"], "properties": {
                "name": {"type": "string"}, "text": {"type": "string"}, "writes": {"type": "boolean"}, "required": {"type": "boolean"}}}},
            "later": {"type": "array", "items": {"type": "string"}, "description": "Other connections they mentioned, one line each, to do next"},
        },
    },
}

OPENING = {
    "api": "Which website or app is it, and what should the brain do with it?",
    "database": "Which database is it, and what should the brain read from it? It will only ever read.",
    "other": "What do you want to connect, and what should the brain do with it?",
}

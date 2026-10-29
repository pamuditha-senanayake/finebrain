# hq2_docs.py: the documents behind Finebase HQ-2: policies, meeting transcripts, Slack and WhatsApp threads, emails, billing, bank and
# tax notes, grants and decks. Each is (doc id, platform, title, domain, sensitivity, date, paragraphs). All people and numbers are made up.
# Read by hq2_world.py (knowledge items) and hq2_history.py (Library records). Platforms: hq2_cast.py.

# Policies: (key, name, rule kind, versions). A version is (n, valid_from, valid_to, [statements]); the newest has valid_to None.
POLICIES = [
    ("policy_client_comms", "Client communication policy", "approval", [
        (1, "2026-07-01", "2026-09-15", ["The project lead sends client updates when they judge the work is ready to show.", "A client who asks for an update is answered the same working day."]),
        (2, "2026-09-15", None, ["A steward approves every message to a client before it is sent, whether it is a weekly update, a video or a reply.",
                                 "A weekly update goes to each active client by Friday 17:00 Colombo time, in the client's own channel.",
                                 "A client who asks for an update is answered within 4 working hours, and the answer names what changed since the last update."])]),
    ("policy_refund", "Client refund and credit policy", "refund", [
        (1, "2026-07-01", "2026-09-01", ["A client may ask for a refund within 7 days of paying an invoice.", "Refunds up to USD 200 inside the window are approved automatically."]),
        (2, "2026-09-01", None, ["A client may ask for a refund within 14 days of paying an invoice.", "Refunds up to USD 500 inside the window are approved automatically.",
                                 "Refunds above USD 500, or requests after 14 days, need approval from the founder."])]),
    ("policy_spend", "Spend and subscription policy", "spend", [
        (1, "2026-07-01", "2026-10-01", ["Monthly cloud spend (Blaze plan) has a budget of USD 700 and tools and subscriptions a budget of USD 500."]),
        (2, "2026-10-01", None, ["Monthly cloud spend (Blaze plan) has a budget of USD 900 and tools and subscriptions a budget of USD 600.",
                                 "Any new tool or subscription above USD 50 a month needs the founder's approval before it is bought.",
                                 "Spend is reviewed on the 5th of each month. Spend more than 20 percent over budget raises an alert to the founder."])]),
    ("policy_tasks", "Task ownership policy", "task", [
        (1, "2026-08-01", None, ["Every task agreed in a meeting has one owner and a due date, written down within 24 hours of the meeting.",
                                 "The owner gets a reminder the day before the task is due. A task with no progress for 3 days is raised with the project lead."])]),
    ("policy_payments", "Payment terms policy", "payments", [
        (1, "2026-07-01", None, ["Invoices are issued through Stripe and are due 15 days after issue. A project starts after the first 50 percent is paid.",
                                 "Clients outside the US may pay by bank transfer to Wise or Mercury. Contractors are paid from Wise on the 28th of each month."])]),
    ("policy_data", "Recording and data handling policy", "data", [
        (1, "2026-08-01", None, ["Meeting recordings and transcripts are kept 180 days, then deleted. Clients are told at the start of a recorded meeting.",
                                 "Client personal data is masked before an agent reads it. Only a steward can see the original."])]),
]

# Other documents: (id, platform, title, domain, sensitivity, date, [paragraphs])
DOCS = [
    # --- Meetings (A2, A3)
    ("doc_meet_lanka_1013", "meet", "Lanka Print weekly meeting 13 Oct", "customer_care", "confidential", "2026-10-13", [
        "Ruwan: Last week we shipped the order list. This week the client wants filters on the tracking page, by status and by date. Kavindu, can you take the filters?",
        "Kavindu: Yes, I will build the filters and push them to staging by Thursday. Sachini will send the new status icons by Wednesday evening.",
        "Client (Nadeesha): Good. We also need the delivery report as a PDF before the 24th for our board. Ruwan: We will confirm that by Friday and send a short update after the meeting."]),
    ("doc_meet_ocean_1015", "meet", "Ocean Foods sync 15 Oct", "customer_care", "confidential", "2026-10-15", [
        "Client (Dilan): The ordering screen is slow on older phones. Kavindu: We measured it, the menu images are too large. I will compress them and send a new build on Monday.",
        "Imashi: Dilan, you asked about the second payment. It is due on the 20th, an invoice goes out Friday. Dilan: Fine, we will pay by bank transfer, is that ok? Ruwan: Yes, to the Wise details on the invoice.",
        "Decision: launch date moves from 30 October to 6 November because of the image fix and the app store review."]),
    ("doc_meet_bluebird_1016", "meet", "Bluebird Clinics review 16 Oct", "customer_care", "confidential", "2026-10-16", [
        "Client (Dr. Mala): Patients can book but the reminder SMS is not arriving. Imashi: We will check the SMS provider settings today and tell you what we find tomorrow.",
        "Sachini: I will redo the booking confirmation screen with larger text by Friday. Kavindu: And I will add the clinic's second branch to the booking form by Tuesday.",
        "Dr. Mala asked whether the monthly fee covers adding a third branch in December. Imashi: We will send a short answer on that after checking the agreement."]),
    ("doc_meet_harbor_1020", "meet", "Harbor Logistics kickoff phase 2, 20 Oct", "customer_care", "confidential", "2026-10-20", [
        "Client (Sameera): Phase 2 is the driver app. We want live location and a signature on delivery. Ruwan: We will break it into three weeks and send you the plan.",
        "Kavindu: I will start the location service this week. Tharushi: I will set up the new GitHub repository and the Blaze project for the driver app on Wednesday.",
        "Decision: weekly update every Friday in the shared Slack channel, with a short video of the app."]),
    ("doc_meet_kandy_1022", "meet", "Kandy Tea Traders check-in 22 Oct", "customer_care", "confidential", "2026-10-22", [
        "Client (Prasad): The cart page shows the wrong total when two coupons are used. Kavindu: Understood. We will fix the coupon rule and test it with your three coupons by Monday.",
        "Prasad also asked for a video walkthrough of the new checkout. Sachini: I will record it on Friday and send it on WhatsApp.",
        "Ruwan reminded the team that the second invoice for Kandy Tea is overdue by 6 days and Tharushi will send a polite reminder."]),
    ("doc_meet_nila_1023", "meet", "Nila Learning first sprint review 23 Oct", "customer_care", "confidential", "2026-10-23", [
        "Client (Anushka): The teacher login works. Students cannot upload homework files larger than 5 MB. Kavindu: We will raise the limit to 20 MB and add a progress bar by Wednesday.",
        "Imashi: Please send us the list of classes for November. Anushka: Yes, I will email it on Monday.",
        "Decision: pilot starts with two schools on 9 November. Imashi will write the first weekly update."]),
    ("doc_meet_internal_1026", "meet", "Team stand-up 26 Oct", "operations", "internal", "2026-10-26", [
        "Ruwan: Three things from last week were not done: the Ocean Foods image fix, the Bluebird SMS check and the Harbor repository. Kavindu said he did the image fix on Friday but did not post it.",
        "Pamuditha: From now on every task said out loud goes into the list the same day. Tharushi, please send me the tools and subscriptions list by Wednesday so we can check the spend.",
        "Tharushi: The Blaze bill for October is already higher than September because of the Harbor test project. I will check which projects cause it."]),
    ("doc_meet_internal_1019", "meet", "Team stand-up 19 Oct", "operations", "internal", "2026-10-19", [
        "Pamuditha: We agreed last week that every client gets an update by Friday. Two clients did not hear from us. Ruwan: Lanka Print and Kandy Tea. We will fix this with a draft each Thursday.",
        "Sachini: I am waiting for the Ocean Foods logo files. Imashi: I asked for them on WhatsApp on Monday and have no answer yet."]),
    # --- Slack (A1, A3, A5)
    ("doc_slack_lanka_1014", "slack", "Slack #lanka-print 14 Oct", "customer_care", "confidential", "2026-10-14", [
        "Nadeesha (client): Any update on the filters? We have a call with our board on Friday. Ruwan: The filters are on staging now. Kavindu will confirm the date filter works with the 3 test accounts.",
        "Kavindu: Date filter works. Status filter shows an empty list for cancelled orders, fixing now. Pushed fix at 16:40."]),
    ("doc_slack_lanka_1022", "slack", "Slack #lanka-print 22 Oct", "customer_care", "confidential", "2026-10-22", [
        "Nadeesha (client): Can we get the delivery report as a PDF? And what is the status of the invoice we got last week, is the second payment due on the 24th or the 31st?",
        "Tharushi: The October invoice is due on the 31st, issued on the 16th with 15 days to pay. The PDF report is with Ruwan for review."]),
    ("doc_slack_bluebird_1017", "slack", "Slack #bluebird 17 Oct", "customer_care", "confidential", "2026-10-17", [
        "Dr. Mala (client): Still no reminder SMS today. Imashi: We found the sender name was not approved by the provider. We have asked them to approve it, usually 2 working days.",
        "Dr. Mala: Fine. Please let me know as soon as it works. Imashi: Yes, we will message here the moment it is approved."]),
    ("doc_slack_harbor_1024", "slack", "Slack #harbor 24 Oct", "customer_care", "confidential", "2026-10-24", [
        "Sameera (client): Week 1 of the driver app, what did you do? Kavindu: Location service reads the phone position every 10 seconds and saves it. Next: the map screen. Video attached.",
        "Sameera: Good. When do we see the signature screen? Ruwan: Week 3, around 12 November."]),
    ("doc_slack_internal_1027", "slack", "Slack #team-tasks 27 Oct", "operations", "internal", "2026-10-27", [
        "Ruwan: Reminder: Ocean Foods image fix, Bluebird SMS check and Harbor repository are open since 19 Oct. Owners please reply with progress.",
        "Kavindu: Image fix done and sent to Ocean Foods on 26 Oct. Tharushi: Repository for Harbor created, Blaze project created, access given to Kavindu.",
        "Sachini: Waiting for logo files from Ocean Foods, blocked since Monday."]),
    # --- WhatsApp (A1, A5)
    ("doc_wa_ocean_1021", "whatsapp", "WhatsApp Ocean Foods 21 Oct", "customer_care", "confidential", "2026-10-21", [
        "Dilan: Any update? We are told the app is ready to test. Imashi: A new build with the image fix was sent yesterday. Here is a 2 minute video of the ordering screen.",
        "Dilan: The video is nice. Can we pay the second payment half now and half after launch? Imashi: We will check with Pamuditha and tell you by tomorrow."]),
    ("doc_wa_ocean_1022", "whatsapp", "WhatsApp Ocean Foods 22 Oct", "customer_care", "confidential", "2026-10-22", [
        "Imashi: Dilan, the founder said the second payment of USD 3,100 is due on the 20th as agreed, and we can accept half on the 20th and half on the 6th of November if you confirm in writing.",
        "Dilan: Confirmed. Please send the bank details again. Imashi: Sent the Wise USD details on your invoice email."]),
    ("doc_wa_kandy_1023", "whatsapp", "WhatsApp Kandy Tea 23 Oct", "customer_care", "confidential", "2026-10-23", [
        "Prasad: Did you fix the coupon problem? Udayanga: It will be fixed on Monday, as we said in the meeting. I will send a short video of it working.",
        "Prasad: And how much do I still owe? Udayanga: The September invoice of USD 3,900 is unpaid, the October one is not issued yet."]),
    ("doc_wa_kandy_1027", "whatsapp", "WhatsApp Kandy Tea 27 Oct", "customer_care", "confidential", "2026-10-27", [
        "Udayanga: Prasad, the coupon fix is live. Here is a video with your three coupons. Prasad: Great, I will pay the September invoice today.",
        "Prasad: Is there a refund if the storefront launch is late? Udayanga: Our policy gives a refund within 14 days of paying an invoice, up to USD 500 automatically."]),
    # --- Gmail (A1, A5, A6)
    ("doc_mail_nila_1005", "gmail", "Email Nila Learning onboarding 5 Oct", "customer_care", "confidential", "2026-10-05", [
        "From Anushka: We would like to start a pilot with two schools. Please send the agreement and the payment details. We can pay by card or bank transfer.",
        "Reply from Imashi: The agreement is attached, the monthly fee is USD 4,300 and the first 50 percent is due before we start. You can pay by card through the Stripe link or by transfer to Wise."]),
    ("doc_mail_nila_1026", "gmail", "Email Nila Learning invoice question 26 Oct", "customer_care", "confidential", "2026-10-26", [
        "From Anushka: The Stripe link says USD 2,150 but our finance team expected USD 2,300. Which is correct?",
        "Reply draft: The first payment is 50 percent of USD 4,300, which is USD 2,150. The USD 2,300 figure in the earlier email included a one-off setup fee that was removed on 8 October."]),
    ("doc_mail_grant_1012", "gmail", "Email Open Research Fund call 12 Oct", "finance", "internal", "2026-10-12", [
        "The Open Research Fund opens its autumn call for small teams building tools for local language education. Awards up to USD 25,000. Deadline 30 November 2026.",
        "Required: a 2 page summary, a budget, a letter from one partner school, and a plan to share the results openly."]),
    # --- Finance platforms (A4, A5, A8)
    ("doc_blaze_aug", "blaze", "Blaze plan invoice August 2026", "finance", "confidential", "2026-09-02", [
        "Blaze plan invoice for August 2026: USD 412.30. Projects: Lanka Print portal USD 148.10, Ocean Foods app USD 131.60, Bluebird booking USD 82.40, other USD 50.20."]),
    ("doc_blaze_sep", "blaze", "Blaze plan invoice September 2026", "finance", "confidential", "2026-10-02", [
        "Blaze plan invoice for September 2026: USD 538.90. Projects: Lanka Print portal USD 171.30, Ocean Foods app USD 156.00, Bluebird booking USD 96.20, Kandy Tea store USD 61.40, other USD 54.00."]),
    ("doc_blaze_oct", "blaze", "Blaze plan usage October 2026 (to 27 Oct)", "finance", "confidential", "2026-10-27", [
        "Blaze usage to 27 October: USD 1,140.20. Forecast for the month: USD 1,260.45. Harbor driver app test project USD 402.10, Ocean Foods app USD 188.50, Lanka Print portal USD 176.80.",
        "The Harbor test project runs location writes every 10 seconds from 40 test devices, which caused the extra cost. The October cloud budget is USD 900, so the forecast is 40 percent over budget."]),
    ("doc_subs_oct", "gdrive", "Tools and subscriptions list October 2026", "finance", "confidential", "2026-10-28", [
        "Subscriptions per month: Slack USD 87.50, Notion USD 64.00, Figma USD 90.00, GitHub Team USD 44.00, Google Workspace USD 126.00, Zoom USD 29.99, Linear USD 56.00, WhatsApp Business API USD 38.00.",
        "Total USD 535.49 against a budget of USD 600. Linear was added on 12 October without approval. Notion is used by nobody since August except for the old board."]),
    ("doc_stripe_oct", "stripe", "Stripe payouts and invoices October 2026", "finance", "confidential", "2026-10-28", [
        "Paid in October: Lanka Print Co. USD 4,800 on 7 Oct, Bluebird Clinics USD 5,400 on 9 Oct, Harbor Logistics USD 7,100 on 15 Oct, Ocean Foods USD 3,100 on 21 Oct (half of the second payment).",
        "Unpaid: Kandy Tea Traders USD 3,900 (September, 6 days late), Nila Learning USD 2,150 (first payment, due 31 Oct). Stripe fees this month USD 596.20."]),
    ("doc_wise_oct", "wise", "Wise transfers October 2026", "finance", "confidential", "2026-10-28", [
        "Contractor payments from Wise on 28 October: Kavindu Perera USD 1,450, Sachini Fernando USD 1,320, Tharushi Silva USD 1,100. Wise fees USD 21.40.",
        "Incoming Wise payment: Ocean Foods USD 1,550 on 21 Oct, matched to the second invoice."]),
    ("doc_mercury_oct", "mercury", "Mercury account summary October 2026", "finance", "restricted", "2026-10-28", [
        "Mercury operating account balance on 28 October: USD 41,860.15. Inflows this month USD 24,350.00, outflows USD 19,742.05 including payroll, Blaze, subscriptions and the Delaware registered agent fee.",
        "A card payment of USD 120.00 to an unfamiliar vendor on 25 October is waiting to be matched to a receipt."]),
    ("doc_llc_checklist", "gdocs", "US LLC setup checklist", "legal", "confidential", "2026-03-20", [
        "Finebase Labs LLC was formed in Delaware on 12 March 2026. The EIN was issued on 25 March. The Mercury business account was opened on 2 April, Wise Business on 9 April and Stripe was activated on 17 April.",
        "Recurring: Delaware annual report and franchise tax due 1 March each year, registered agent renewal due 12 March each year, Form 5472 with pro-forma Form 1120 due 15 April each year."]),
    ("doc_tax_notes", "gdocs", "Tax and filing notes 2026", "legal", "confidential", "2026-10-10", [
        "Because the LLC is owned by a non-US person, Form 5472 and a pro-forma 1120 must be filed even with no US tax due. The penalty for a missing 5472 is USD 25,000. The accountant needs the bank statements for the year by 15 February.",
        "Sales tax: none charged, services delivered abroad. Revisit if a US client is signed."]),
    # --- Notion / GitHub (A3, A11)
    ("doc_notion_board", "notion", "Notion Ocean board export", "operations", "internal", "2026-10-25", [
        "The board has 31 cards. 22 are in Doing. The last card moved was on 21 August. Cards still name two former members. Nobody on the team reads the board.",
        "Decision proposed on 25 October: stop using the board and let the brain keep the task list from meetings."]),
    ("doc_github_week43", "github", "GitHub merged pull requests, week of 19 Oct", "product", "internal", "2026-10-26", [
        "Merged: PR 214 Tracking page filters (Kavindu), PR 217 Compress menu images (Kavindu), PR 219 Coupon stacking rule (Kavindu), PR 221 Location service (Kavindu).",
        "Open longer than a week: PR 208 Booking form second branch (Kavindu), PR 212 Reminder SMS sender name (Imashi)."]),
    # --- Docs: what we build, grants, decks (A6, A7, A9)
    ("doc_what_we_build", "gdocs", "What we build: Finebase Labs services", "product", "internal", "2026-09-28", [
        "Finebase Labs builds web portals, mobile apps and storefronts for small and mid-sized businesses in Sri Lanka and abroad. A project has phases: discover, design, build, launch and care.",
        "Each phase ends with a client update: a short written report and a video. We use a fixed monthly fee, billed in USD. This page is out of date for the Harbor and Nila projects; the sections for the driver app and the learning platform are missing."]),
    ("doc_grant_draft", "gdocs", "Open Research Fund application draft", "finance", "internal", "2026-10-22", [
        "Summary: We will build an open reading-practice tool for Sinhala and Tamil primary schools, tested in the Nila Learning pilot with two schools. Requested amount USD 25,000 over 8 months.",
        "Budget draft: developers USD 14,000, design USD 4,000, school coordination USD 3,000, cloud USD 1,500, evaluation USD 2,500. Missing: letter from a partner school, open results plan."]),
    ("doc_deck_hackathon", "gdrive", "Hackathon pitch deck: Cargo Hack 2026", "sales", "internal", "2026-10-18", [
        "Deck outline: problem (delivery drivers lose proof of delivery), demo (Harbor driver app), traction (three logistics clients), ask (a pilot with a regional carrier). 8 slides, draft 2.",
        "The hackathon is on 14 and 15 November in Colombo. Team of four: Ruwan, Kavindu, Sachini and Imashi. Deck due to the organisers by 12 November."]),
    ("doc_contract_lanka", "gdrive", "Master services agreement Lanka Print Co.", "legal", "confidential", "2026-07-01", [
        "Finebase Labs LLC provides the order tracking portal for a monthly fee of USD 4,800. Payment terms: invoice due 15 days after issue. Either party may end the agreement with 30 days notice.",
        "Changes after the first signed scope are billed at USD 55 an hour, agreed in writing before work starts."]),
]

# Verified facts (the vault): (id, predicate, subject type, subject key, statement, raw value, normalized, valid_from, source doc)
FACTS = [
    ("fact_llc_formed", "llc_formed", "company", "finebase labs llc", "Finebase Labs LLC was formed in Delaware on 12 March 2026.", "2026-03-12", "2026-03-12", "2026-03-12", "doc_llc_checklist"),
    ("fact_5472_2025", "form_5472_filed", "company", "finebase labs llc", "Form 5472 for 2025 was not needed: the LLC was formed in 2026.", "n/a", "n/a", "2026-03-12", "doc_tax_notes"),
    ("fact_blaze_aug", "cloud_spend", "spend", "blaze 2026-08", "Blaze plan spend for August 2026 was USD 412.30.", "USD 412.30", "41230", "2026-08-01", "doc_blaze_aug"),
    ("fact_blaze_sep", "cloud_spend", "spend", "blaze 2026-09", "Blaze plan spend for September 2026 was USD 538.90.", "USD 538.90", "53890", "2026-09-01", "doc_blaze_sep"),
    ("fact_subs_oct", "subscription_total", "spend", "subscriptions 2026-10", "Tools and subscriptions for October 2026 total USD 535.49.", "USD 535.49", "53549", "2026-10-01", "doc_subs_oct"),
    ("fact_stripe_oct", "revenue_paid", "revenue", "stripe 2026-10", "Client payments received through Stripe in October 2026 total USD 20,400 by 28 October.", "USD 20,400", "2040000", "2026-10-01", "doc_stripe_oct"),
]

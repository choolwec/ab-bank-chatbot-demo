<!-- Source content for V2 RAG chunking (§4.1). V1 answers live in
     intents/*.yaml — keep the two in sync.
     Sourced primarily from Branch Staff FAQ Document and the Social Media
     Response Template (12.08.2025) — these two documents are the priority
     source and override anything below marked [WEB]. Facts marked [WEB] are
     supplementary research (AB Bank's own site blocks automated fetching, so
     these are drawn from Wikipedia, LinkedIn, Bank of Zambia filings, and
     search-indexed snippets of abbank.co.zm) and should be confirmed with
     marketing/compliance before publishing verbatim. -->

# About AB Bank Zambia

## Who is AB Bank

AB Bank is a licensed local commercial bank operating in Zambia, regulated by
the Bank of Zambia. It provides banking and credit solutions to individuals,
SMEs, corporates, NGOs, churches, and associations through its branch
network. [Branch Staff FAQ]

Per the Social Media Response Template: AB Bank Zambia has been operating in
Zambia for 14 years (as of the 12 August 2025 template) and has 9 branches
and 1 satellite branch. [SOCIAL MEDIA TEMPLATE — note: this branch count is
narrower than the branch list actually enumerated with addresses in the same
document; see `branches.json` and the discrepancy note there.]

[WEB] AB Bank Zambia began operations on 18 October 2011 under a commercial
banking licence from the Bank of Zambia — consistent with "14 years" as of
the 2025 documents. It is majority-owned by AccessHolding (the international
microfinance network also behind AB Bank Rwanda and others), with FMO, the
International Finance Corporation (IFC), Incofin, and KfW each holding
minority stakes. This ownership detail is public (Wikipedia, LinkedIn) but
not confirmed by either priority document — treat as background, not
verbatim customer-facing copy, until marketing confirms.

## Services offered

- Current (transactional) accounts — Tamanga, Tamanga Plus, Mukula Plus
- Savings and investment accounts — Savings, Savings Plan, Kids Savings,
  Term Deposit Account (TDA)
- Personal and business loans
- Digital and mobile banking services — eTumba wallet, Online Banking
  (MyABZ)
- Local and international transfers, and international remittance receipt
  via RIA and Remitly

[Branch Staff FAQ]

## What AB Bank does not currently offer

AB Bank Zambia does not currently operate its own branded ATMs. eTumba
supports cardless withdrawal at ATMs via the mobile-network-operator (MNO)
cardless option, and cash-out at Kazang / 543 Konse Konse / Zoona agents —
see `etumba.md`. [SOCIAL MEDIA TEMPLATE] There is no debit/ATM card product
mentioned in either priority document. [WEB, unconfirmed against the two
priority documents: an older (2016-era) Wikipedia summary lists "debit
cards" among AB Bank Zambia's historical products — this appears stale
against the 2025 internal documents' explicit "we do not have ATMs"
statement. Confirm current card status with product/marketing before the
chatbot asserts either way.]

## Branch network and locations

See `branches.json` for the full list with addresses, phone numbers, and
sort codes. Branches operate in Lusaka (multiple), Kitwe, Ndola, Chipata,
Solwezi, and a satellite office in Mumbwa. [Branch Staff FAQ / SOCIAL MEDIA
TEMPLATE]

If asked about branches in other towns: AB Bank does not yet have a branch
there; direct the customer to follow AB Bank's social media and website for
news of new locations. [SOCIAL MEDIA TEMPLATE]

## Regulator and compliance status

[WEB] The Bank of Zambia's own branch-network publication (dated November
2025, the most recent found) lists AB Bank Zambia Limited as a licensed bank
with branches/agencies matching most of the two priority documents' list,
plus one additional location — a Chongwe promotional office — not mentioned
in either priority document. This is flagged for ops/branch-network
confirmation rather than treated as settled fact; see `branches.json`.

## Website and portals

- Main website: www.abbank.co.zm [SOCIAL MEDIA TEMPLATE references this
  domain repeatedly, e.g. the personal-loan page path below]
- Personal loan pre-approval form: www.abbank.co.zm/personal-loan
  [SOCIAL MEDIA TEMPLATE]
- Online Banking (MyABZ) portal: https://ob.abbank.co.zm/landing/auth
  [SOCIAL MEDIA TEMPLATE; "MyABZ" branding confirmed via the portal's own
  terms-of-use page title, found in web research]
- HR / careers portal: https://hr.abbank.co.zm [SOCIAL MEDIA TEMPLATE]

[CONFIRM: AB Bank's own website (abbank.co.zm) refused automated fetches
during this research pass (connection-level block, likely bot/WAF
protection), so its content could only be checked via third-party
search-index snippets, not read directly. Before launch, someone with a
normal browser should verify the tariff-guide link, personal-loan page, and
quick-links page still match what's written here.]

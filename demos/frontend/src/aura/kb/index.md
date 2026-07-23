---
id: index
title: Aura Bank — L1 Support Knowledge Base
title_en: Aura Bank — L1 Support Knowledge Base
category: index
---

# Aura Bank L1 Support Knowledge Base

The knowledge an L1 (top-of-funnel) support assistant needs to resolve common
**self-service, no-login** customer questions — the "how do I…" tasks that don't
require the customer's logged-in account context. The assistant **explains and
shows** (it plays the relevant official Aura how-to video and narrates it); it
never transacts on the customer's behalf.

This folder is the single source of truth: each article and each video below is a
markdown file with structured front-matter that the demo app and the voice agent
both read.

## How videos are used (the key capability)

`videos/*.md` index Aura's **official how-to videos** by timed **chapters**
(derived from the real video transcripts). Each chapter has a `start`/`end`
second, an on-screen `label`, and a Hindi `say` line. The assistant pulls the
right video, **jumps to the exact second**, plays it **muted**, and narrates the
steps in its own words — so the customer gets the answer **visually and verbally
at once**.

| Video | Covers | File |
|---|---|---|
| `M_Oxpto2PRo` | Interest Certificate (tax) | `videos/M_Oxpto2PRo.md` |
| `Mv_Tktxl40s` | Debit-card PIN / limits / lock | `videos/Mv_Tktxl40s.md` |
| `i8SJ-9wAB1o` | Register on app + Net Banking | `videos/i8SJ-9wAB1o.md` |
| `VxO3yJmBuRE` | Fund transfer / add payee | `videos/VxO3yJmBuRE.md` |

## Most common questions (start here)

1. **"Tax ke liye interest certificate kahan se milega?"** →
   [`interest-certificate`](loans-deposits/interest-certificate.md) · video `M_Oxpto2PRo`
2. **"Card kho gaya / PIN reset karna hai"** →
   [`debit-card-pin-and-controls`](cards/debit-card-pin-and-controls.md) · video `Mv_Tktxl40s` ·
   [`block-credit-card`](cards/block-credit-card.md)
3. **"Net banking / app pe register kaise karun?"** →
   [`register-mobile-and-netbanking`](netbanking/register-mobile-and-netbanking.md) · video `i8SJ-9wAB1o`
4. **"Paise kaise bhejun / payee add karna hai"** →
   [`fund-transfer-add-payee`](payments/fund-transfer-add-payee.md) · video `VxO3yJmBuRE`

## Categories

- **Cards** — `cards/`: debit-card PIN & controls, block credit card, bill
  payment, Aura Rewards.
- **Accounts** — `accounts/`: open a savings account, KYC / re-KYC, minimum
  balance, cheque book.
- **Aura NetBanking & App** — `netbanking/`: register on app + net banking, reset MPIN.
- **Payments** — `payments/`: fund transfer & add payee, UPI/IMPS/NEFT/RTGS limits.
- **Loans & Deposits** — `loans-deposits/`: interest certificate, TDS certificate,
  home-loan statement, open an FD.
- **Support** — `support/`: helpline numbers, branch/ATM & IFSC locator, grievance
  redressal.

## Ground rules for the assistant

- **No login = no transaction.** Many tasks are account-specific. The assistant
  shows *where* and *how*; the customer does the actual download/transfer on their
  own login. Say so plainly when `needs_login: true`.
- **Never ask for OTP, PIN, CVV, or password.**
- When the customer is stuck or it's genuinely account-specific, fall back to the
  **helpline** (`1860-200-0100`) or branch.

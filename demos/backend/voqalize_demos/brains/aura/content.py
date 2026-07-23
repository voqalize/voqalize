# ruff: noqa: RUF001  # prose facts use en-dashes, ₹, and other typographic unicode
"""Curated Aura Bank reference facts for the aura banking-support demo.

Fictional bank; a de-branded snapshot of a generic Indian retail bank's
public help content. Interpolated into the brain's system prompt so the
assistant answers general questions with consistent (invented) figures.
"""

AURA_FACTS = """# Aura Bank common pre-auth facts

<!-- Reference knowledge distilled from Aura Bank's public site. Rates/fees/limits
     are a snapshot retrieved 10 July 2026 and are subject to change. Copied from
     the assistant knowledge base (level-1). -->

## Phone numbers and urgent help

| Need | Number / channel |
|---|---|
| Retail phone banking | **1860 200 0100**, **1860 200 0200** (chargeable); **1800 200 0300** (toll-free) |
| 24-hour card-blocking emergency | **+91 40 2000 0100** (not toll-free) |
| Debit-card emergency | **+91 22 2000 0200** |
| National cybercrime reporting | **1930**; cybercrime.gov.in |
| Official WhatsApp Banking | **7000000100**; send `Hi` |
| SMS Banking | **5000100**; NRI: **+919900000002** |
| FASTag customer care / block tag | **1800 200 0400** (toll-free) |
| FASTag balance missed call | **7000000200** |
| NHAI FASTag/toll help | **1033** |
| NRI phone banking from India | **1800 200 0350**; **040 2000 0100** (chargeable) |
| Branch/ATM locator | branch.aura.bank.example |

## Fraud and card controls

### Unrecognised transaction / scam

- Aura complaint: website **Support > Report a Fraud**.
- Financial/cybercrime: **1930** or cybercrime.gov.in.
- Fraudulent SMS/call/WhatsApp received within 30 days: Chakshu (sancharsaathi.gov.in).
- RBI complaint: RBI Complaint Management System (cms.rbi.org.in); RBI phone **14440**.

### Block a debit card

- SMS: `BLOCKCARD <last 4 digits>` to **5000200** or **+919900000003**.
- Internet Banking: **Debit Cards > Block Card**.
- Open app: **Banking > Services > Debit Cards > Block & Replace**.
- Emergency: **+91 22 2000 0200**.

### Block/control a credit card

- SMS block: `BLOCK <last 4 digits>` to **5000100** or **+919900000002**.
- Open app / Internet Banking: **Credit Card > Control Center**.
- IVR: **1860 200 0200** / **1860 200 0100**.

### Set/reset card PIN

| Card | Channel | Path |
|---|---|---|
| Debit | Open app | **Banking > Services > Debit Card > Set/Reset PIN** |
| Debit | Internet Banking | **Cards > Debit Cards > Change PIN** |
| Debit | Aura ATM | **Set PIN**; registered mobile number, DOB and activation passcode |
| Credit | Open app | **Banking > Services > Credit Card > Set/Reset PIN** |
| Credit | Internet Banking | **Accounts > My Credit Cards > More Services > Credit Card PIN Change** |
| Credit | Aura ATM | **Set PIN**; DOB, card expiry, registered mobile and OTP |
| Credit | IVR | **1860 200 0100 / 1860 200 0200 > PIN Related Services** |

- Credit-card IVR/ATM activation code: valid **3 hours or one use**, whichever is earlier.
- Online-card pre-OTP: `PREOTP <last 4 card digits>` to **5000100**; valid **30 minutes** for one transaction.

### Enable/disable card usage and change limits

- Debit app: **Banking > Services > Debit Cards > Manage Usage > Domestic/International Usage**.
- Debit Internet Banking: **Services > Debit Card Services > select card > More Services > Manage Usage**.
- Debit ATM/purchase limits can be changed; setting limits to zero temporarily switches usage off without permanently blocking the card.
- Credit app/Internet Banking: **Credit Card > Control Center > Domestic Usage / International Usage**.
- Replacement or upgraded cards require transaction functions to be enabled again.
- International card transactions may not use OTP.

### Re-KYC fraud warning

- Re-KYC through branch, Internet Banking, mobile banking or official Aura support channels.
- Aura says not to share personal/financial details over calls or emails claiming to update Re-KYC.

## Current rates snapshot — July 2026

Rates below were retrieved **10 July 2026** and are subject to change.

### Fixed Deposit rates

Domestic FD key rates:

| Deposit / tenure | General | Senior citizen |
|---|---:|---:|
| Less than ₹3 crore; 1 year–1 year 10 days | **6.25%** | **6.75%** |
| ₹3 crore–less than ₹5 crore; 1 year–1 year 10 days | **6.25%** | **6.75%** |
| Less than ₹3 crore; 18 months–less than 2 years | **6.50%** | **7.00%** |
| ₹3 crore–less than ₹5 crore; 18 months–less than 2 years | **6.60%** | **7.10%** |

NRE FD key rates: **6.25%** for 1 year–1 year 10 days; **6.50%** below ₹3 crore and **6.60%** for ₹3 crore–less than ₹5 crore for 18 months–less than 2 years.

- Regular FD minimum deposit: **₹5,000**.
- Regular FD tenure: **7 days to 10 years**.
- Monthly-interest option: select **Monthly Payout** when opening the FD.
- FD interest is taxable; TDS depends on current tax rules and projected aggregate FD interest.

### FD opening, closure and loan

- Minimum opening amount: **₹5,000 online/app; ₹10,000 at branch**.
- Premature withdrawal: available for most FDs; lower applicable rate/penalty may apply. Five-year Tax Saver FD cannot be prematurely withdrawn.
- Liquidity without closure: loan/overdraft available against eligible FD.
- Eligible jointly held FD/RD: primary holder initiates digital closure; joint holder approves the same day.
- Renewal: Internet Banking or branch.

### Recurring Deposit rates and terms

Rates below ₹3 crore, effective on the source from **22 December 2025**:

| Tenure | General | Senior citizen |
|---|---:|---:|
| 6 months | **5.50%** | **6.00%** |
| 9 months | **5.75%** | **6.25%** |
| 12 months | **6.25%** | **6.75%** |
| 15–48 months | **6.45%** | **6.95%** |
| 60 or 120 months | **6.45%** | **7.20%** |

- Minimum monthly deposit: **₹500**; tenure: **6 months–10 years**.
- Delayed instalment: **₹10 per ₹1,000 overdue per month**.
- Published premature rate for deposits under ₹5 crore: **1% below contracted rate**.
- Open: Internet Banking **Deposits > Create Recurring Deposit**; Open app **Deposits > Open RD**; or branch.

### Savings Account interest

- Domestic/NRO/NRE balance below ₹2,000 crore: **2.50% p.a.**
- ₹2,000 crore and above: **Overnight MIBOR + 1.01%** under the published slab rules.
- Effective date on source: **3 April 2026**.
- Interest calculation: daily closing balance; credit frequency depends on account type. The page states quarterly credit for a standard Savings Account.

### Common retail-loan rates

| Product | Published current rate / key charge |
|---|---|
| Personal Loan | **9.99%–22% p.a.** advertised range; processing fee up to **2% + GST** |
| Home Loan, CIBIL 751+ | **8.00%–8.85% p.a.** |
| Home Loan, CIBIL ≤750 / no history | **8.20%–9.10% p.a.** |
| Fixed Home Loan | **14.00% p.a.** |
| New Car Loan | **8.90%–11.70% p.a.**; processing fee up to **2% + GST**; documentation **₹700 + GST** |
| Two-Wheeler Loan | **15.00%–25.00% p.a.** published effective range |
| Gold Loan | **9.75%–17.00% p.a.** |
| Loan Against Property | **9.25%–10.00% p.a.** |
| Loan Against Securities | **11.50%–13.75% p.a.** |

## Credit-card bill and payments

### Pay from Aura Internet Banking

**Credit Cards > select card > Pay now > Last Billed Due or Minimum Due > Confirm and Pay > OTP**.

### Pay from Open app

**Quick Links > Credit Cards > select card > Pay now > Last Billed Due or Minimum Due > Confirm and Pay > mPIN**.

### Auto Debit

- App: **Services > Credit Card > Auto Debit Payment > select card > Activate**.
- Internet Banking: **Services > Credit Card Services > select card > More Services > Auto Debit Setup**.
- Auto Debit may be set for total amount due or minimum amount due from an Aura savings/current account.

### Other payment methods

| Method | Published details |
|---|---|
| Aura ATM | **Other Services > Bill Payment**; same-day processing |
| Cash at Aura branch | **₹100 per payment**; same-day processing |
| Cheque/draft | Payable to `Aura Bank Card No. <16-digit card number>`; deposit at least 5 days before due date |
| UPI | Pay Credit Card Bill in UPI app; verify recipient; published TAT 2 working days |
| NEFT | Beneficiary: name on card; bank Aura Bank; branch Mumbai; account = 16-digit card number; IFSC **AURA0000400**; published TAT 1 working day |

- Full payment by due date avoids interest on carried balance. Paying only minimum due carries the remainder with interest.
- Aura's catalogue page says carried credit-card balances typically incur **3%–4% monthly** interest; exact rate is card-specific.

## Internet, mobile, WhatsApp and SMS Banking

### Customer ID / Internet Banking

- Customer ID: welcome letter or cheque book.
- SMS Customer ID: `CUSTID <full 15-digit account number>` to **5000100** from registered mobile.
- Registration: Internet Banking > **Register here** > Customer ID or registered mobile > available Debit Card/OTP/email/KYC verification.
- Forgotten password: login page **Forgot Password** > Customer ID > offered Debit Card/email/KYC verification > OTP > new password.
- Five consecutive failed NETSECURE-code attempts disable transaction validation for the day; published automatic re-enable after 24 hours.
- Internet Banking services: balances, statements, transfers, bill pay, cheque book, stop cheque, demand draft, FD and portfolio.

### Open by Aura Bank app

- Accounts: balance, mini/detailed statements, transfer, bill pay/recharge.
- Cards: outstanding/available limit, bill payment, PIN, block/replace, usage/transaction limits.
- Deposits/loans: open FD/RD, loan statement, repayment schedule, interest certificate.
- Requests: cheque book, cheque status, stop cheque, e-statement email, PAN/email update.

### Open app registration and mPIN

- Registration requires the bank-registered mobile SIM; on dual-SIM devices it must be selected as primary. Verification SMS must be sent unchanged.
- Level 1: install app > Login > permit call/SMS access > verification SMS > name/terms > set six-digit mPIN/biometric.
- Full customer access: authenticate with Internet Banking, debit-card credentials, or Customer ID/DOB/PAN plus OTPs; standalone card/forex/loan customers use product details.
- Forgot mPIN: **Forgot MPIN > Internet Banking or Debit Card option > registered mobile > activation code > new mPIN**.
- New-device registration automatically deregisters the prior device.
- Five consecutive incorrect mPIN entries lock the app; **Forgot MPIN** provides reset.
- Newly registered mobile number: published wait **24 hours** before app registration.
- Transaction-limit modification: available after **5 days** from registration. Re-registration resets first-five-day default to **₹30,000** for non-Private and **₹1 lakh** for Private.

### WhatsApp Banking

- Verified Aura number: **7000000100**; send `Hi`, `Start` or `Sign-up`.
- Services: balance, mini statement, cheque book, nominee, FD/RD, credit/debit card, loans, FASTag.
- Unsubscribe: send `STOP` and confirm.

### Common SMS keywords

Send from registered mobile to **5000100** or **+919900000002**.

| Need | SMS format |
|---|---|
| Balance | `BAL [account number]` |
| Last 3 transactions | `MINI [account number]` |
| E-statement | `ESTMT <last 5 account digits> <from DD-MM-YYYY> <to DD-MM-YYYY>` |
| Credit-card available limit | `AVAILBAL <last 4 card digits>` |
| Credit-card outstanding | `CARDBAL <last 4 card digits>` |
| Last credit-card payment | `LASTPAY <last 4 card digits>` |
| Block credit card | `BLOCK <last 4 card digits>` |
| Block debit card | `BLOCKCARD <last 4 card digits>` |
| Cheque book | `CHQBK <last 6 account digits>` |
| Cheque status | `CHQST <6 cheque digits> <last 6 account digits>` |
| PAN update | `PAN <PAN> <Customer ID>` |
| ATM locator | `ATM <PIN code>` |
| FASTag balance | `FTGBAL <vehicle number>` |

## UPI and bank transfers

### UPI setup and payment

- Verify registered mobile number > select bank/account > create UPI ID > set UPI PIN with debit-card credentials and OTP.
- Merchant website/app: choose **Pay by UPI** > enter UPI ID > review notification and transaction details > enter UPI PIN.
- Store: scan merchant QR, enter amount, verify merchant and enter UPI PIN; or approve a merchant collect request after checking details.

### UPI failure, limits and PIN reset

- Failed transaction with account debit: source states amount is credited back instantly.
- Timed-out transaction: beneficiary credit or reversal within **2 working days**.
- General P2P/P2M debit limit: **₹1 lakh per transaction and cumulative per 24 hours**; P2P maximum **20 transactions per 24 hours**.
- New UPI user or changed device/SIM: **₹5,000 per 24 hours** during cooling period; iOS cooling period is **72 hours**.
- UPI mandate: **₹1 lakh**; IPO mandate: **₹5 lakh**; IPO 24-hour limit: **₹15 lakh**.
- Aadhaar PIN reset requires the Aadhaar-linked mobile to match the UPI-app mobile. Two wrong Aadhaar entries disable Aadhaar reset for **24 hours**; debit-card reset remains available.
- UPI Lite: maximum wallet balance **₹2,000**; stolen-handset manual refund published TAT **5 working days**.

### RuPay credit card on UPI

- Link in supported UPI app: **Add/Link Credit Card > Aura Bank > card > last 6 digits + expiry > OTP > separate UPI PIN**.
- Use: merchant QR/UPI ID only; person-to-person payments and cash withdrawal are not allowed.
- No Aura charge for linking or transactions; available credit limit and UPI-category limits apply.

### Transfer methods

| Method | Availability / limit | Charges and failure facts |
|---|---|---|
| IMPS | **24×7×365**; **₹5 lakh per transaction**; immediate credit | Inward free. Outward: up to ₹1,000 **₹2.50**; ₹1,000–₹1 lakh **₹5**; ₹1–₹5 lakh **₹10**; tax extra. Pending: wait **2 days** for reversal/credit. |
| NEFT | **24×7×365**; no system minimum/maximum; account limits apply | Online free. 11:30pm–1am transactions settle at 2am. Non-credit returned within 2 hours of batch. After-hours/holiday online limit **₹1 crore per transaction**; larger payment processes next banking period. |
| RTGS | **24×7×365**; minimum **₹2 lakh**; no system maximum | Online free; branch may charge. 11:30pm–1am transactions settle at 2am. After-hours/holiday online limit **₹1 crore per transaction**. |

- IMPS fraud/general/wrong-credit chargeback: raise within **45 days**; published response TAT **25 days + 2 days internal processing**.
- NEFT/RTGS Customer Facilitation Centre: **022 2000 0300**, **cfc@aurabank.example**.

## Re-KYC, profile updates, statements and applications

### Individual Savings / Salary / HUF Re-KYC

| Channel | Path |
|---|---|
| Open app | **Services > My Profile > Update KYC** |
| Internet Banking | **Services > My Profile > Confirm KYC** |
| Website support | **Insta Services > My Details > Update KYC** |
| Branch | Signed Re-KYC form + acceptable documents |

- No address change: confirm address.
- Address changed: select change and proof of address.

### PAN/contact/address updates

- Internet Banking contact details: **My Profile > Update Contact details**.
- Open app PAN: **Insta Services > Update PAN**.
- SMS PAN: `PAN <PAN> <Customer ID>` to **5000200**.
- Residential address: customer-request form submitted at branch.
- Registered mobile: Aura ATM or customer-request form at branch.

### Statements, ATM and cash deposit

- e-statements: past **3 years** through online/app; older statements at branch; e-statements free.
- ATM: balance, last 7 transactions/mini statement, PIN change, cheque-book request.
- Cash Deposit Machine: cash deposit using debit card or 15-digit account number; successful transaction credited instantly; availability varies by location.

### Cheque book, cheque status and stop payment

- Open app cheque book: **Banking > Services > Savings/Current Account > New Cheque Book**; default **20 leaves**; one request per day.
- Open app stop cheque: select by date or cheque number; only unused/unpaid cheques; authenticate with mPIN.
- Internet Banking stop payment: submitted successful request is processed immediately.
- SMS cheque book: `CHQBK <last 6 account digits>`.
- SMS cheque status: `CHQST <6 cheque digits> <last 6 account digits>`.
- SMS stop cheque: `STOPCHQ <6 cheque digits> <last 6 account digits> <reason code>`.
- Cheque-book charges are account-specific.

### Utility and other bill payments

- Open app: **Pay > Recharges & Bills > category > biller > details > View My Bill > Pay Now**.
- Categories include mobile, electricity, gas, water, broadband, DTH, FASTag, landline, insurance, loan repayment, credit cards and rent.
- New biller: first 24 hours published limit **₹10,000** and maximum **2 transactions** in each category.

### Application status

- General product status: Application Tracker on aurabank.example.
- Home Loan / Car Loan tracking: Application ID or PAN on the linked loan tracker.

## FASTag

- Buy: fastag.aura.bank.example, Open app, Aura branch or authorised offline channel.
- Recharge: FASTag portal, Internet Banking/Open app, NEFT/IMPS, UPI, BBPS, WhatsApp or toll-plaza POS.
- UPI VPA: `netc.<registered mobile>@aurabank` or `netc.<vehicle registration>@aurabank`.
- Portal/app: balance, recharge, transaction history and disputes.
- Current issuance fee: **₹100 including tax**.
- Current reissuance fee: **₹100 including tax**.
- Current minimum recharge: **₹100**.
- Lost/block/reissue: **1800 200 0400**.
- Balance missed call: **7000000200**.
- Toll-reader issue / NHAI: **1033**.

## Digital Savings Account

### Eligibility

- Indian citizen; age **18+**.
- Valid PAN and Aadhaar; Aadhaar-linked mobile.
- Applying from India; camera and internet for Video KYC.
- Digital Savings Account is single-holder; joint account is not available under this journey.

### Current published variants

| Variant | Initial funding | Balance / plan requirement |
|---|---:|---|
| Easy Access Digital | Metro ₹16,000; Urban ₹15,000; Semi-urban/Rural ₹10,000 | AMB: Metro/Urban ₹12,000; Semi-urban ₹5,000; Rural ₹2,500 |
| Amaze Digital | ₹10,000 | Nil AMB; ₹200/month with 6-month minimum or ₹2,200/year plan charge |
| Liberty Digital | ₹25,000 | ₹25,000 AMB or ₹25,000 monthly spends |
| Prestige Digital | ₹75,000 | ₹75,000 AMB |
| Priority Digital | ₹2 lakh | ₹2 lakh AMB |
| Private Digital | ₹5 lakh | ₹10 lakh AQB |

## Loan documents and basic terms

### Personal Loan

- Published amount: **₹50,000–₹50 lakh**.
- Basic documents: identity, address, PAN and income proof; online applications may request recent salary slips and **6 months' bank statements**.

### Home Loan

- Published minimum amount: **₹3 lakh**; maximum tenure **30 years**. Maximum amount is product/profile-specific.
- Salaried documents: identity/address KYC, recent salary slips, Form 16 and bank statements.
- Self-employed documents: ITR/financial statements and bank statements; property documents also required.
- Published typical sanction: **5 business days** after required documents; disbursement after documentation/property appraisal may take up to **15 days**.

## Locker and nominee

### Safe Deposit Locker

- Apply at an Aura branch; locker agreement required.
- Carry one original KYC document, applicable state/UT stamp paper and one recent photo per applicant.
- Sizes: small, medium, large and extra-large; rent varies by size/location.
- Free visits: **7 per calendar month**; then **₹100 + GST per visit**.
- Late rent penalty: **₹100 + GST**.
- Nomination supported; locker rent can be paid from the locker page.

### Account nominee

- Digital Savings nominee may be skipped during opening and added later.
- WhatsApp Banking lists **Update your nominee** under account services.
"""

/**
 * Contract content for the Docket demo — mirrors the legal brain's backend
 * content by hand. The text must match; the ids no longer can drift, since
 * {@link ClauseId} is read off the generated actions and so off the brain.
 */

import type { PointToClause } from './actions.gen';

/** The ten clauses of this contract — the only ids the assistant can name. */
export type ClauseId = PointToClause['clause_id'];

export interface Clause {
  id: ClauseId;
  number: string;
  heading: string;
  text: string;
}

export const MATTER = {
  client: 'Acme Robotics, Inc.',
  counterparty: 'Nimbus Cloud Systems, Inc.',
  documentTitle: 'Master Services Agreement',
  governingLaw: 'Delaware',
};

export const CLAUSES: Clause[] = [
  {
    id: 'c1',
    number: '1',
    heading: 'Services',
    text: 'Nimbus Cloud Systems, Inc. (“Vendor”) shall provide Acme Robotics, Inc. (“Customer”) with access to Vendor’s fleet-telemetry cloud platform (the “Services”) as described in each Order Form, including hosting, data ingestion, and analytics dashboards for Customer’s robotics fleet. Vendor shall perform the Services in a professional and workmanlike manner consistent with generally accepted industry standards.',
  },
  {
    id: 'c2',
    number: '2',
    heading: 'Term & Termination',
    text: 'This Agreement commences on the Effective Date and continues for an initial term of thirty-six (36) months, automatically renewing for successive twelve (12) month terms unless either party gives ninety (90) days’ written notice of non-renewal. Either party may terminate for the other party’s uncured material breach following thirty (30) days’ written notice. Customer may terminate for convenience upon one hundred eighty (180) days’ written notice, subject to payment of a wind-down fee equal to twenty-five percent (25%) of the remaining committed contract value.',
  },
  {
    id: 'c3',
    number: '3',
    heading: 'Fees & Payment',
    text: 'Customer shall pay the fees set forth in each Order Form within thirty (30) days of invoice. Fees are non-refundable except as expressly stated herein. Vendor may increase fees upon renewal by no more than five percent (5%) annually over the prior term’s fees, with sixty (60) days’ advance notice. Late payments accrue interest at one and one-half percent (1.5%) per month or the maximum rate permitted by law, whichever is lower.',
  },
  {
    id: 'c4',
    number: '4',
    heading: 'Confidentiality',
    text: 'Each party shall protect the other’s Confidential Information using at least the same degree of care it uses for its own confidential information of similar importance, and in no event less than reasonable care. Confidentiality obligations survive termination for a period of five (5) years, except with respect to trade secrets, which shall be protected for as long as the information retains trade secret status under applicable law.',
  },
  {
    id: 'c5',
    number: '5',
    heading: 'Data Protection',
    text: 'Vendor shall process Customer Personal Information solely as necessary to provide the Services and in accordance with the California Consumer Privacy Act, as amended by the California Privacy Rights Act (CCPA/CPRA), and other applicable US data-protection law. Vendor shall implement commercially reasonable administrative, technical, and physical safeguards designed to protect Customer Personal Information. Vendor shall notify Customer of a confirmed data breach affecting Customer Personal Information without undue delay, and in no event later than seventy-two (72) hours after Vendor becomes aware of the breach.',
  },
  {
    id: 'c6',
    number: '6',
    heading: 'Intellectual Property',
    text: 'As between the parties, Customer retains all right, title, and interest in Customer Data and Customer’s pre-existing intellectual property. Vendor retains all right, title, and interest in the Services, the underlying platform, and any general learnings, provided such learnings do not include and cannot be used to reconstruct Customer Data. Vendor grants Customer a non-exclusive, non-transferable license to use the Services during the term solely for Customer’s internal business purposes.',
  },
  {
    id: 'c7',
    number: '7',
    heading: 'Indemnification',
    text: 'Vendor shall defend, indemnify, and hold harmless Customer against any third-party claim alleging that the Services infringe a US patent, copyright, or trade secret, and shall indemnify Customer for breaches of Vendor’s confidentiality and data-protection obligations under Sections 4 and 5. Customer shall indemnify Vendor against third-party claims arising from Customer’s misuse of the Services in violation of this Agreement.',
  },
  {
    id: 'c8',
    number: '8',
    heading: 'Limitation of Liability',
    text: 'EXCEPT FOR A PARTY’S INDEMNIFICATION OBLIGATIONS UNDER SECTION 7, NEITHER PARTY SHALL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES. EACH PARTY’S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATED TO THIS AGREEMENT SHALL NOT EXCEED TWO HUNDRED FIFTY THOUSAND DOLLARS ($250,000), REGARDLESS OF THE THEORY OF LIABILITY, AND REGARDLESS OF WHETHER EITHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.',
  },
  {
    id: 'c9',
    number: '9',
    heading: 'Insurance',
    text: 'Vendor shall maintain, at its own expense, commercial general liability insurance with limits of not less than $2,000,000 per occurrence, technology errors and omissions insurance with limits of not less than $3,000,000 per claim, and cyber liability insurance with limits of not less than $3,000,000 per claim, and shall provide Customer with certificates of insurance upon request.',
  },
  {
    id: 'c10',
    number: '10',
    heading: 'Governing Law & Dispute Resolution',
    text: 'This Agreement shall be governed by the laws of the State of Delaware, without regard to its conflict-of-laws principles. Any dispute arising out of or relating to this Agreement shall be resolved by binding arbitration administered by the American Arbitration Association (AAA) under its Commercial Arbitration Rules, seated in Wilmington, Delaware, before a single arbitrator. Either party may seek injunctive relief in a court of competent jurisdiction to protect its intellectual property or Confidential Information.',
  },
];

export const CLAUSES_BY_ID = Object.fromEntries(
  CLAUSES.map((c) => [c.id, c]),
) as Record<ClauseId, Clause>;

export interface DataRoomDoc {
  id: string;
  name: string;
  description: string;
}

// Mirrors the backend's DATA_ROOM — other documents attached to this matter,
// grounding the "pull across the data room" / "litigation history" asks.
export const DATA_ROOM: DataRoomDoc[] = [
  {
    id: 'd1',
    name: 'Nimbus MSA — this draft',
    description: 'The Master Services Agreement currently under review.',
  },
  {
    id: 'd2',
    name: 'Nimbus MSA — Order Form No. 1',
    description: 'Initial order form: fleet-telemetry platform scope, fees, and term.',
  },
  {
    id: 'd3',
    name: 'Nimbus DPA Amendment (2024)',
    description: 'Prior data-processing addendum amendment already on file for this vendor.',
  },
  {
    id: 'd4',
    name: 'Nimbus litigation & background search',
    description: 'External docket/records search on Nimbus Cloud Systems, Inc. and its principals.',
  },
];

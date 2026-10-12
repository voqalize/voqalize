/**
 * Solution pages (footer, Solutions column). Each has its own route in
 * src/pages/solutions/<id>.astro, its own pieces in src/components/solutions/<id>/
 * and its own styles in src/styles/solutions/<id>.css. Notes: docs/sections/solutions-<id>.md.
 */
export interface SolutionLink { slug: string; title: string }
export const SOLUTIONS: SolutionLink[] = [
  { slug: 'solutions/retail', title: 'Retail and e-commerce' },
  { slug: 'solutions/banking', title: 'Banking' },
  { slug: 'solutions/insurance', title: 'Insurance' },
  { slug: 'solutions/healthcare', title: 'Healthcare' },
  { slug: 'solutions/legal', title: 'Legal' },
  { slug: 'solutions/support', title: 'Customer support' },
];

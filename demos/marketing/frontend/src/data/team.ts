/**
 * The people on the About page (/about). Edit this one file to add, remove or update anyone.
 *
 * - `photo`: a path under /public, e.g. '/about/team/samkeet-jain.webp'. Square, at least 800 x 800.
 *   Every portrait sits in the same square frame. Leave it `null` and the page draws a placeholder
 *   (initials and a "Photo coming" tag), so a missing photo never breaks the grid.
 * - `line`: one short, light line shown on the card. Draft lines are waiting for each person's approval
 *   (see docs/sections/page-about.md, open questions).
 * - `bio`: founders only, a few sentences. `null` shows a visible "Bio: to come" placeholder.
 * - `links`: optional, e.g. [{ label: 'LinkedIn', href: 'https://www.linkedin.com/in/...' }].
 */
export interface Person {
  name: string;
  role: string;
  photo: string | null;
  line: string | null;
  bio?: string | null;
  links?: { label: string; href: string }[];
}

export const FOUNDERS: Person[] = [
  { name: 'Samkeet Jain', role: 'Co-founder', photo: null, bio: null,
    line: 'Has pitched voice to anyone who stood still for 200 milliseconds.' },
  { name: 'Sripathi Krishnan', role: 'Co-founder', photo: null, bio: null,
    line: 'Thinks every app will talk soon, and keeps a list of the ones running late.' },
  { name: 'Swetha Suresh', role: 'Co-founder', photo: null, bio: null,
    line: 'Asks the app a question every morning and expects a better answer by evening.' },
];

export const TEAM: Person[] = [
  { name: 'Abhishek Kumar Singh', role: 'Software Engineer', photo: null,
    line: 'Taught the app to stop talking mid-sentence. Meetings are next.' },
  { name: 'Ashwini Kumar Singh', role: 'Product Designer', photo: null,
    line: 'Designs the screens, then designs the way to skip them by asking.' },
  { name: 'Abhineet Srinivasa', role: 'Software Engineer', photo: null,
    line: 'Writes the code for "actually, make it Tuesday." Then for "no, Wednesday."' },
  { name: 'Ramsha Iqbal', role: 'Software Engineer', photo: null,
    line: 'Trained the noise filter to ignore dogs, televisions and one particular kettle.' },
  { name: 'Aditi Tiwari', role: 'Product Manager', photo: null,
    line: 'Writes specs short enough for the app to read aloud in one breath.' },
  { name: 'Itish Srivastava', role: 'Software Engineer', photo: null,
    line: 'Tests every audio change on a train going into a tunnel.' },
  { name: 'Mohit Chawla', role: 'Customer Success', photo: null,
    line: 'Asks "can you hear me?" on every customer call, and means it as a product question.' },
];

/** Two letters for the placeholder portrait: first and last name. */
/** Everyone, in the order the page shows them: one grid, no split between founders and team. */
export const PEOPLE: Person[] = [...FOUNDERS, ...TEAM];

export const initials = (name: string) => {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
};

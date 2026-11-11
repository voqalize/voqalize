/**
 * Who answers the call. `?avatar=tushar` puts the `tushar` character in the tile
 * instead of `ananya`; each key is the character's name in `@voqalize/avatar`. The brain gives each face its own name, voice and grammatical
 * gender (`backend/brain.py` → `_PERSONAS`), because a face read as one gender
 * speaking in the other is the first thing anyone notices; this is the page-side
 * half, so every line that would have said "Aria" names whoever is on the call.
 */

export type AuraFace = 'ananya' | 'tushar';

const NAMES: Record<AuraFace, string> = { ananya: 'Aria', tushar: 'Tushar' };

export const agentName = (face: AuraFace): string => NAMES[face];

/** Read once, like the page's other flags: the character is a property of the load. */
export const PAGE_FACE: AuraFace =
  new URLSearchParams(window.location.search).get('avatar') === 'tushar' ? 'tushar' : 'ananya';

export const AGENT_NAME = agentName(PAGE_FACE);

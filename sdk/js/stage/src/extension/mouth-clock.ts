/**
 * The mouth clock on a page: the holder's newest delivery of his voice,
 * answered as of the moment the face reads it.
 *
 * The face reads `getSynchronizationSources()` when it draws and treats an
 * answer as late as a stop: once what it reads is more than a frame and a gap
 * old, it shuts the mouth, and a page has no sound of its own to hold it open.
 * A receiver in the page answers fresh at every read. The relayed one answers
 * with the last message the page got round to, and a busy page (a gallery, a
 * scroll, the next page parsing) gets round to it late: measured in Chromium,
 * a page with 60 ms of work every 120 ms shut the mouth on 43 % of the reads
 * made while he spoke, against 18 % for a read in the voice's own document.
 *
 * So the page carries the newest delivery forward to the read, at the RTP
 * clock's rate, as a receiver would have stamped it had audio kept arriving,
 * and for no longer than `HOLD_MS` past it. Past that it stays put, which is a
 * stop as the face reads one: a real pause, or a page busier than that.
 */

/** Opus over RTP is always clocked at 48 kHz. */
const RTP_PER_MS = 48;
const WRAP = 2 ** 32;
/**
 * How far past the newest delivery a read may be carried. The relay samples
 * every 23 ms, so a quiet page is never more than about that behind; this
 * covers a page busy for a few frames more. It is also how much longer the
 * mouth may run over a real stop before the face sees it, close to the 150 ms
 * the face holds through concealment when it can hear the voice itself.
 */
export const HOLD_MS = 100;

/** One delivery: when (epoch ms, the page's and holder's shared wall clock)
 *  and which RTP timestamp. */
export interface Delivery {
  timestamp: number;
  rtpTimestamp: number;
}

/** The delivery a receiver would report at `now` (epoch ms), carried forward
 *  from `newest`; null before there is one. */
export function carriedForward(newest: Delivery | null, now: number): Delivery | null {
  if (!newest) return null;
  const ahead = Math.max(0, Math.min(HOLD_MS, now - newest.timestamp));
  return {
    timestamp: newest.timestamp + ahead,
    rtpTimestamp: (newest.rtpTimestamp + Math.round(ahead * RTP_PER_MS)) % WRAP,
  };
}

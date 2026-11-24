import { BRAND } from "../data/product";

/** The brand mark from product.json, beside the wordmark. */
export function Logo({ size = 32, word = true }: { size?: number; word?: boolean }) {
  return (
    <span className="logo">
      <span className="logo-mark" style={{ width: size, height: size }} aria-hidden dangerouslySetInnerHTML={{ __html: BRAND.logo_svg }} />
      {word ? <span className="logo-word">{BRAND.name}</span> : <span className="sr-only">{BRAND.name}</span>}
    </span>
  );
}

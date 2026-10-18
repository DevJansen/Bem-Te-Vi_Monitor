/**
 * Imagem padrão para espécies sem foto (silhueta do sistema).
 *
 * Quando uma detecção não foi identificada — ou quando a foto tratada de uma
 * espécie está ausente/corrompida — exibimos esta **silhueta** acompanhada do
 * rótulo "Pássaro Desconhecido". Assim nunca aparece um ícone de imagem
 * quebrada e a nomenclatura fica consistente em todo o aplicativo.
 *
 * A silhueta é um SVG *inline* convertido em *data URI*: não exige um arquivo
 * binário no bundle e escala sem perda de nitidez.
 */
const SILHUETA_BIRD_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="Pássaro Desconhecido">
  <rect width="120" height="120" rx="14" fill="#0b1512"/>
  <path d="M30 80c14-3 22-15 27-26 4-9 12-16 22-16 5 0 9 2 11 5 1 2 0 4-3 4-5 0-5 4-2 7 5 5 12 7 19 7-5 11-16 18-28 20-10 2-19 8-28 10-9 2-17-1-18-11z"
        fill="#34d399" opacity="0.92"/>
  <circle cx="85" cy="42" r="2.6" fill="#0b1512"/>
  <path d="M93 42l9 3-9 3z" fill="#f59e0b"/>
  <path d="M46 84c8 0 15 1 22 0-6 5-15 6-22 0z" fill="#0b1512" opacity="0.25"/>
</svg>`;

/** Data URI da silhueta padrão de pássaro. */
export const BIRD_SILHOUETTE_DATA_URI = `data:image/svg+xml,${encodeURIComponent(
  SILHUETA_BIRD_SVG.trim(),
)}`;

/** Data URI de uma "pata" (visitantes especiais/mamíferos) para contraste. */
const SILHUETA_PATA_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="Visitante Especial">
  <rect width="120" height="120" rx="14" fill="#0b1512"/>
  <ellipse cx="60" cy="76" rx="26" ry="22" fill="#f59e0b" opacity="0.85"/>
  <circle cx="34" cy="48" r="10" fill="#f59e0b" opacity="0.85"/>
  <circle cx="52" cy="38" r="10" fill="#f59e0b" opacity="0.85"/>
  <circle cx="72" cy="38" r="10" fill="#f59e0b" opacity="0.85"/>
  <circle cx="90" cy="48" r="10" fill="#f59e0b" opacity="0.85"/>
</svg>`;

/** Data URI de uma pata (para visitantes especiais sem foto). */
export const PAW_SILHOUETTE_DATA_URI = `data:image/svg+xml,${encodeURIComponent(
  SILHUETA_PATA_SVG.trim(),
)}`;

/**
 * The mark of Nines: the empty dinner jacket of the app's icon and its shadow, without the icon's cream square, so it
 * sits on any background. Drawn from frontend/scripts/nines-icon.svg (the source of the icons); change the two
 * together. The jacket's outer edge is `.nines-edge`, which a dark theme lightens so the black cloth still has an
 * outline (styles.css, `--brand-edge`). Decoration only: the name beside it is the text.
 */
export function NinesMark({ className = '' }: { className?: string }) {
  return (
    <svg className={`nines-mark ${className}`.trim()} viewBox="124 118 268 366" aria-hidden="true" focusable="false">
      <ellipse className="nines-shadow" cx="249.6" cy="470" rx="88.8" ry="10.6" fill="#000" opacity=".16" />
      <g transform="translate(256 258) rotate(2.8) scale(1.16) scale(-.86 .96) translate(-256 -262)" strokeLinejoin="round">
        <path d="M346,318 L347,328 Q362,331 375,322 L375,312 Z" fill="#fff" stroke="#cfd3d8" strokeWidth="3" />
        <path className="nines-edge" d="M334,180 C356,188 370,208 372,238 L376,314 Q360,312 344,321 L338,240 Z" fill="#101112" stroke="#17191a" strokeWidth="6" />
        <path className="nines-edge" d="M182,368 Q262,343 354,360 Q268,398 182,368 Z" fill="#33383e" stroke="#17191a" strokeWidth="6" />
        <path className="nines-edge" d="M218,160 C190,166 168,176 160,196 L170,260 L182,368 Q262,343 354,360 C357,326 366,296 360,262 C356,224 350,196 338,178 C328,168 316,162 306,158 Z" fill="#17191a" stroke="#17191a" strokeWidth="6" />
        <g fill="none" stroke="#868d95" strokeWidth="3.5" strokeLinecap="round">
          <path d="M338,178 C350,196 356,224 360,262 C366,296 357,326 354,360" />
          <path d="M182,368 Q262,343 354,360" />
        </g>
        <path d="M240,166 L312,160 L298,318 Z" fill="#fff" />
        <path d="M312,160 L298,318 L290,232 Z" fill="#e3e5e8" />
        <path d="M298,330 L302,357" fill="none" stroke="#868d95" strokeWidth="3.5" strokeLinecap="round" />
        <path d="M244,152 Q278,146 308,150 L282,190 Z" fill="#33383e" stroke="#868d95" strokeWidth="3.5" />
        <path d="M216,170 L234,150 L248,162 L298,318 L282,340 L226,274 L256,258 L208,232 Z" fill="#4d535a" stroke="#868d95" strokeWidth="3.5" />
        <path d="M328,162 L318,148 L308,158 L298,318 L312,336 L340,264 L322,252 L346,226 Z" fill="#4d535a" stroke="#868d95" strokeWidth="3.5" />
        <path d="M244,151 L237,172 L258,202 L280,188 Z" fill="#fff" stroke="#cfd3d8" strokeWidth="3" />
        <path d="M308,149 L314,166 L300,198 L283,188 Z" fill="#fff" stroke="#cfd3d8" strokeWidth="3" />
        <g fill="#17191a">
          <path d="M240,176 Q233,194 240,212 L276,199 L276,188 Z" />
          <path d="M316,179 Q321,193 316,207 L284,199 L284,188 Z" />
          <rect x="272" y="184" width="16" height="19" rx="4" />
          <circle cx="288" cy="230" r="5.5" />
          <circle cx="291" cy="260" r="5.5" />
          <circle cx="294" cy="290" r="5.5" />
        </g>
        <path d="M135,319 L135,330 Q158,340 182,334 L182,323 Z" fill="#fff" stroke="#cfd3d8" strokeWidth="3" />
        <path d="M142,331 Q158,338 176,333 Q158,330 142,331 Z" fill="#8f959c" />
        <path className="nines-edge" d="M198,168 C166,172 140,192 136,236 L132,322 Q158,314 185,326 L200,246 C203,214 201,190 198,168 Z" fill="#17191a" stroke="#17191a" strokeWidth="6" />
        <path d="M198,170 C203,196 203,222 200,246 L186,326" fill="none" stroke="#868d95" strokeWidth="3.5" strokeLinecap="round" />
      </g>
    </svg>
  );
}

/** The name as it is written wherever it is the app's name on a screen: in the brand's serif. */
export function NinesName() {
  return <span className="nines-name">Nines</span>;
}

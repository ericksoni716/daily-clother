/** The outline of one shoe from its side, toe to the left: where to place the shoe in the photo. Drawn over the
 * camera and over the photo just taken. */
export function ShoeGuide({ className }: { className?: string }) {
  const shoe = 'M22 118 Q16 104 30 96 Q70 86 116 72 Q146 52 172 42 Q198 34 214 46 Q238 56 260 40 '
    + 'Q280 34 284 52 L286 104 Q287 121 270 122 L36 122 Q24 122 22 118 Z';
  return (
    <svg className={className ?? 'shoe-guide'} viewBox="0 0 300 150" aria-hidden="true" focusable="false" data-testid="shoe-guide">
      <path d={shoe} fill="none" stroke="rgba(0,0,0,.55)" strokeWidth="5" strokeLinejoin="round" />
      <path d={shoe} fill="none" stroke="#fff" strokeWidth="2.5" strokeDasharray="9 6" strokeLinejoin="round" />
      <path d="M20 135 L290 135" stroke="#fff" strokeWidth="2" strokeDasharray="4 6" />
      <text x="18" y="147" fill="#fff" stroke="rgba(0,0,0,.6)" strokeWidth="3" paintOrder="stroke" fontSize="12">toe</text>
      <text x="262" y="147" fill="#fff" stroke="rgba(0,0,0,.6)" strokeWidth="3" paintOrder="stroke" fontSize="12">heel</text>
    </svg>
  );
}

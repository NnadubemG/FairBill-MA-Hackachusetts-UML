import type { Flag } from '@contracts';

const BASIS_LABEL: Record<string, string> = {
  medicare_reference: 'Compared with Medicare reference',
  ma_price_range: 'Compared with Massachusetts price range',
  duplicate_detection: 'Possible duplicate',
  eob_mismatch: 'Compared with your Explanation of Benefits',
  arithmetic_check: 'Math check',
  coding_heuristic: 'Billing-code check',
  other: 'Worth a look',
};

export function Flags({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  return (
    <ul className="flags">
      {flags.map((f, i) => (
        <li key={i} className="flag">
          <span className="flag-basis">{BASIS_LABEL[f.basis] ?? 'Worth a look'}</span>
          <span className="flag-explanation">{f.explanation}</span>
        </li>
      ))}
    </ul>
  );
}

/** Help section linking to official Massachusetts resources. */
import { MA_RESOURCES } from '../config/resources';

export function Resources() {
  return (
    <section className="resources" aria-labelledby="resources-heading">
      <h2 id="resources-heading">Massachusetts resources that may help</h2>
      <p>
        These official and nonprofit resources offer free help understanding bills,
        coverage, and assistance programs.
      </p>
      <ul>
        {MA_RESOURCES.map((r) => (
          <li key={r.url}>
            <a href={r.url} target="_blank" rel="noopener noreferrer">
              {r.label}
            </a>
            <span className="resource-desc"> — {r.description}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

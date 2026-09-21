import { Component, input } from '@angular/core';

/**
 * The "human judgement has the final say" notice. `note` is the full version for
 * the report; `compact` is a single line for places with less room.
 */
@Component({
  selector: 'app-disclaimer',
  standalone: true,
  template: `
    @if (variant() === 'note') {
      <aside class="disclaimer note" aria-label="About this analysis">
        <span class="icon" aria-hidden="true">⚖</span>
        <div>
          <strong>You make the final call.</strong>
          <p>
            LegalLens reads every clause in seconds and shows you where to look. It can't know your goals, your
            bargaining position or the law that applies to you, but a person can. Human judgement, ideally a
            qualified lawyer's, should always have the final word on a contract.
          </p>
        </div>
      </aside>
    } @else {
      <p class="disclaimer compact">
        LegalLens shows you where to look; human judgement, ideally a lawyer's, always has the final say.
      </p>
    }
  `,
  styleUrl: './disclaimer.component.css',
})
export class DisclaimerComponent {
  readonly variant = input<'note' | 'compact'>('note');
}

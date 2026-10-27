import { Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AnalysisService } from './analysis.service';

/** Page 3: read-only card; the user's changes in green, what CLIP proposed in red, with CLIP's score. */
@Component({
  selector: 'app-summary-page',
  template: `
    @if (s.analysis(); as analysis) {
      <div class="card" [class.blurry]="s.blurry()">
        <img class="photo" [src]="s.photoUrl()" [alt]="s.altText()">
        <div class="name">
          {{ s.savedAs() }}
          @if (s.blurry()) { <span class="badge">{{ s.t('ui:blurry_badge') }}</span> }
          @if (s.exifText()) { <small class="exif">{{ s.exifText() }}</small> }
        </div>
        <ul class="summary">
          <li>
            <span class="criterion">{{ s.t('ui:date') }}</span>
            <span class="values">{{ s.takenText() }}</span>
          </li>
          @for (row of rows(); track row.name) {
            <li [class.changed]="row.changed">
              <span class="criterion">{{ s.t('c:' + row.name) }}</span>
              <span class="values">
                @if (row.changed) {
                  <span class="mine">{{ s.value(row.name, row.mine) }}</span>
                  @if (row.clip === null) {
                    <span class="clip">{{ s.t('ui:not_assessed') }}</span>
                  } @else {
                    <span class="clip"><s>{{ s.value(row.name, row.clip) }}</s> {{ row.score }}</span>
                  }
                } @else {
                  <span>{{ s.value(row.name, row.mine) }} <small class="score">{{ row.score }}</small></span>
                }
              </span>
            </li>
          }
        </ul>
        <p class="legend">
          <span class="mine">■ {{ s.t('ui:legend_mine') }}</span>
          <span class="clip">■ {{ s.t('ui:legend_clip') }}</span>
        </p>
        <div class="actions">
          <button type="button" class="main" (click)="next()">📷 {{ s.t('ui:new_photo') }}</button>
        </div>
      </div>
    }
  `,
})
export class SummaryPage {
  protected s = inject(AnalysisService);
  private router = inject(Router);

  /** Every criterion that the user or CLIP answered (a criterion can be hidden on one side only). */
  protected rows = computed(() => {
    const analysis = this.s.analysis();
    if (!analysis) return [];
    return this.s.criteria()
      .map(c => {
        const clip = analysis.answers[c.name];
        const mine = this.s.finalValue(c);
        return {
          name: c.name, mine, clip: clip.value, changed: mine !== clip.value,
          score: clip.score === null ? '' : Math.round(clip.score * 100) + ' %',
        };
      })
      .filter(row => row.mine !== null || row.clip !== null);
  });

  protected next(): void {
    this.s.reset();
    this.router.navigate(['/']);
  }
}

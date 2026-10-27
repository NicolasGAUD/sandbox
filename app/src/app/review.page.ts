import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AnalysisService } from './analysis.service';

/** Page 2: CLIP's answers prefill the form; each criterion can be changed with its dropdown. */
@Component({
  selector: 'app-review-page',
  template: `
    @if (s.analysis(); as analysis) {
      <div class="card" [class.blurry]="s.blurry()">
        <img class="photo" [src]="s.photoUrl()" [alt]="s.altText()">
        <div class="name">
          {{ analysis.name }} <small>{{ analysis.time_ms }} ms</small>
          @if (s.blurry()) { <span class="badge">{{ s.t('ui:blurry_badge') }}</span> }
          @if (s.exifText()) { <small class="exif">{{ s.exifText() }}</small> }
        </div>
        <form (submit)="$event.preventDefault(); validate()">
          <div class="row">
            <span class="criterion">{{ s.t('ui:date') }}</span>
            <span>{{ s.takenText() }}</span>
          </div>
          @for (c of s.visible(); track c.name) {
            @let clip = analysis.answers[c.name];
            <label class="row" [class.changed]="s.answers()[c.name] !== clip.value">
              <span class="criterion">
                {{ s.t('c:' + c.name) }}
                @if (clip.score !== null) { <small class="score">{{ percent(clip.score) }}</small> }
              </span>
              <select [value]="s.answers()[c.name]" (change)="change(c.name, $event)">
                @for (v of s.sortedValues(c); track v) {
                  <option [value]="v" [selected]="v === s.answers()[c.name]">
                    {{ s.value(c.name, v) }}{{ v === clip.value ? ' (CLIP)' : '' }}
                  </option>
                }
              </select>
            </label>
          }
          <div class="actions">
            <button type="button" (click)="restart()">{{ s.t('ui:other_photo') }}</button>
            <button type="submit" class="main" [disabled]="busy()">{{ s.t('ui:validate_photo') }}</button>
          </div>
          @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
        </form>
      </div>
    }
  `,
})
export class ReviewPage {
  protected s = inject(AnalysisService);
  private router = inject(Router);
  protected busy = signal(false);
  protected error = signal<string | null>(null);

  protected percent(score: number): string {
    return Math.round(score * 100) + ' %';
  }

  protected change(criterion: string, event: Event): void {
    this.s.setAnswer(criterion, (event.target as HTMLSelectElement).value);
  }

  protected restart(): void {
    this.s.reset();
    this.router.navigate(['/']);
  }

  protected async validate(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.s.validate();
      await this.router.navigate(['/summary']);
    } catch {
      this.error.set(this.s.t('ui:save_failed'));
    } finally {
      this.busy.set(false);
    }
  }
}

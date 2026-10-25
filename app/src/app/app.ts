import { Component, effect, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AnalysisService } from './analysis.service';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  template: `
    <header>
      <strong>{{ s.t('ui:app_title') }}</strong>
      <span class="lang">
        <button type="button" [disabled]="s.lang() === 'fr'" (click)="s.setLang('fr')">FR</button>
        <button type="button" [disabled]="s.lang() === 'en'" (click)="s.setLang('en')">EN</button>
      </span>
    </header>
    <main><router-outlet /></main>
  `,
})
export class App {
  protected s = inject(AnalysisService);

  constructor() {
    effect(() => { document.documentElement.lang = this.s.lang(); });
  }
}

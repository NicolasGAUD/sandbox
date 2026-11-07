import { Component, effect, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AnalysisService } from './analysis.service';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  template: `
    <header>
      <strong>{{ s.t('ui:app_title') }}</strong>
      <span class="settings">
        <!-- Toggle button: its name stays the same, aria-pressed tells whether the dark theme is on. -->
        <button type="button" class="theme" [attr.aria-pressed]="s.theme() === 'dark'"
                [attr.aria-label]="s.t('ui:dark_theme')" [title]="s.t('ui:dark_theme')"
                (click)="s.setTheme(s.theme() === 'dark' ? 'light' : 'dark')">
          <span aria-hidden="true">{{ s.theme() === 'dark' ? '☀' : '☾' }}</span>
        </button>
        <span class="lang" role="group" [attr.aria-label]="s.t('ui:language')">
          <button type="button" [disabled]="s.lang() === 'fr'" (click)="s.setLang('fr')">FR</button>
          <button type="button" [disabled]="s.lang() === 'en'" (click)="s.setLang('en')">EN</button>
        </span>
      </span>
    </header>
    <main><router-outlet /></main>
  `,
})
export class App {
  protected s = inject(AnalysisService);

  constructor() {
    effect(() => { document.documentElement.lang = this.s.lang(); });
    effect(() => { document.documentElement.dataset['theme'] = this.s.theme(); });
  }
}

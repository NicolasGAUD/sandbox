import { HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

/** A criterion shown in the form, as sent by GET /api/config (criteria.json). */
export interface Criterion {
  name: string;
  values: string[];
  /** Hidden when an earlier answer is in the list, e.g. weather except indoor. */
  except: Record<string, string[]>;
  /** Hidden unless an earlier answer is in the list, e.g. vehicle_type only if vehicle. */
  only_if: Record<string, string[]>;
}

type Label = { en: string; fr: string };

export interface Labels {
  criteria: Record<string, Label>;
  values: Record<string, Record<string, Label>>;
  ui: Record<string, Label>;
}

/** CLIP's answer for one criterion; value is null when CLIP's own answers hide the criterion. */
export interface ClipAnswer {
  value: string | null;
  score: number | null;
  detail: Record<string, number>;
}

export interface Analysis {
  id: string;
  name: string;
  time_ms: number;
  answers: Record<string, ClipAnswer>;
}

export type Lang = 'fr' | 'en';

/** App state shared by the three pages: config, current photo, CLIP's answers and the user's ones. */
@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private http = inject(HttpClient);

  readonly criteria = signal<Criterion[]>([]);
  private labels = signal<Labels | null>(null);
  readonly lang = signal<Lang>(readLang());

  readonly photoUrl = signal<string | null>(null);
  readonly analysis = signal<Analysis | null>(null);
  /** The user's answers, prefilled with CLIP's. */
  readonly answers = signal<Record<string, string>>({});
  readonly savedAs = signal<string | null>(null);

  /** Criteria shown for the current answers (the others are hidden by "except" / "only_if"). */
  readonly visible = computed(() => this.criteria().filter(c => isVisible(c, this.answers())));

  async loadConfig(): Promise<void> {
    if (this.labels()) return;
    const config = await firstValueFrom(this.http.get<{ criteria: Criterion[]; labels: Labels }>('/api/config'));
    this.criteria.set(config.criteria);
    this.labels.set(config.labels);
  }

  setLang(lang: Lang): void {
    this.lang.set(lang);
    try { localStorage.setItem('clip-lang', lang); } catch { /* private mode: not remembered */ }
  }

  /** Label of a criterion ("c:name"), a value ("v:criterion:value") or a ui text ("ui:key"). */
  t(key: string, vars: Record<string, string | number> = {}): string {
    const [kind, a, b] = key.split(':');
    const labels = this.labels();
    const entry = !labels ? undefined
      : kind === 'c' ? labels.criteria[a]
      : kind === 'v' ? labels.values[a]?.[b] ?? labels.values['*']?.[b]
      : labels.ui[a];
    let text = entry ? entry[this.lang()] ?? entry.en : key.split(':').pop()!;
    for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
    return text;
  }

  value(criterion: string, value: string | null): string {
    return value === null ? '—' : this.t(`v:${criterion}:${value}`);
  }

  async analyse(file: File): Promise<void> {
    this.reset();
    this.photoUrl.set(URL.createObjectURL(file));
    const form = new FormData();
    form.append('photo', file, file.name);
    const analysis = await firstValueFrom(this.http.post<Analysis>('/api/analyses', form));
    this.analysis.set(analysis);
    // Prefill: CLIP's answer, or for a criterion CLIP hid, its best scored option
    // (used only if the user's changes make the criterion visible).
    const answers: Record<string, string> = {};
    for (const c of this.criteria()) {
      const clip = analysis.answers[c.name];
      answers[c.name] = clip?.value ?? best(clip?.detail ?? {}) ?? c.values[0];
    }
    this.answers.set(answers);
  }

  setAnswer(criterion: string, value: string): void {
    this.answers.update(answers => ({ ...answers, [criterion]: value }));
  }

  /** Final answer: null for a criterion hidden by the user's answers. */
  finalValue(criterion: Criterion): string | null {
    return isVisible(criterion, this.answers()) ? this.answers()[criterion.name] : null;
  }

  async validate(): Promise<void> {
    const analysis = this.analysis()!;
    const answers = Object.fromEntries(this.criteria().map(c => [c.name, this.finalValue(c)]));
    const result = await firstValueFrom(
      this.http.post<{ file: string }>(`/api/analyses/${analysis.id}/validate`, { answers }));
    this.savedAs.set(result.file);
  }

  reset(): void {
    const url = this.photoUrl();
    if (url) URL.revokeObjectURL(url);
    this.photoUrl.set(null);
    this.analysis.set(null);
    this.answers.set({});
    this.savedAs.set(null);
  }
}

export function isVisible(c: Criterion, answers: Record<string, string>): boolean {
  if (Object.entries(c.except).some(([name, values]) => values.includes(answers[name]))) return false;
  return Object.entries(c.only_if).every(([name, values]) => values.includes(answers[name]));
}

function best(detail: Record<string, number>): string | undefined {
  return Object.entries(detail).sort((a, b) => b[1] - a[1])[0]?.[0];
}

function readLang(): Lang {
  try { return localStorage.getItem('clip-lang') === 'en' ? 'en' : 'fr'; } catch { return 'fr'; }
}

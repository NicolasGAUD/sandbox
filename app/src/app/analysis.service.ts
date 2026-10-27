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

/** French agreement of the words that follow a subject: masculine / feminine, singular / plural. */
type Gender = 'm' | 'f' | 'mp' | 'fp';

/** Piece of the image description; an adjective gives its French form for each gender. */
interface AltPhrase {
  en: string;
  fr: string | Partial<Record<Gender, string>>;
  gender?: Gender;
}

export interface Labels {
  criteria: Record<string, Label>;
  values: Record<string, Record<string, Label>>;
  ui: Record<string, Label>;
  alt: Record<string, Record<string, AltPhrase>>;
}

/** Shooting date and camera settings read in the photo; null when the EXIF does not give them. */
export interface Exif {
  /** Local time of the camera, without time zone, e.g. "2017-06-10T14:23:08". */
  taken: string | null;
  camera: string | null;
  exposure_time: number | null;
  f_number: number | null;
  focal_length: number | null;
  iso: number | null;
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
  exif: Exif;
}

export type Lang = 'fr' | 'en';
export type Theme = 'light' | 'dark';

/** App state shared by the three pages: config, current photo, CLIP's answers and the user's ones. */
@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private http = inject(HttpClient);

  readonly criteria = signal<Criterion[]>([]);
  private labels = signal<Labels | null>(null);
  readonly lang = signal<Lang>(readLang());
  readonly theme = signal<Theme>(document.documentElement.dataset['theme'] === 'dark' ? 'dark' : 'light');

  readonly photoUrl = signal<string | null>(null);
  readonly analysis = signal<Analysis | null>(null);
  /** The user's answers, prefilled with CLIP's. */
  readonly answers = signal<Record<string, string>>({});
  readonly savedAs = signal<string | null>(null);

  /** Criteria shown for the current answers (the others are hidden by "except" / "only_if"). */
  readonly visible = computed(() => this.criteria().filter(c => isVisible(c, this.answers())));

  readonly blurry = computed(() => this.answerOf('blurry') === 'yes');

  /** Shooting date in the chosen language; only an EXIF date is shown. */
  readonly takenText = computed(() => {
    const taken = this.analysis()?.exif.taken;
    if (!taken) return this.t('ui:unknown_date');
    // Read and shown as UTC: the camera's local time stays as it was written.
    return new Intl.DateTimeFormat(this.lang(), { dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC' })
      .format(new Date(taken + 'Z'));
  });

  /** "SONY ILCA-68 · 1/500 s · f/8 · 20 mm · ISO 100", with only what the EXIF gives. */
  readonly exifText = computed(() => {
    const exif = this.analysis()?.exif;
    if (!exif) return '';
    const number = (n: number) => n.toLocaleString(this.lang(), { maximumFractionDigits: 1 });
    const t = exif.exposure_time;
    return [
      exif.camera,
      t && (t < 1 ? `1/${Math.round(1 / t)} s` : `${number(t)} s`),
      exif.f_number && `f/${number(exif.f_number)}`,
      exif.focal_length && `${number(exif.focal_length)} mm`,
      exif.iso && `ISO ${Math.round(exif.iso)}`,
    ].filter(Boolean).join(' · ');
  });

  /** Text alternative built from the answers, e.g. "Image d'un château en ruine sous le soleil". */
  readonly altText = computed(() => {
    const alt = this.labels()?.alt;
    if (!alt) return '';
    const lang = this.lang();
    const subject = alt['vehicle_type'][this.answerOf('vehicle_type') ?? '']
      ?? alt['place_type'][this.answerOf('place_type') ?? ''] ?? alt['place_type']['undetermined'];
    const phrase = (criterion: string) => {
      const entry = alt[criterion][this.answerOf(criterion) ?? ''];
      if (!entry) return '';
      if (lang === 'en' || typeof entry.fr === 'string') return entry[lang] as string;
      return entry.fr[subject.gender ?? 'm'] ?? '';
    };
    const words = [phrase('condition'), phrase('weather'), phrase('time_of_day')].filter(Boolean);
    return [this.t('ui:photo_alt', { subject: subject[lang] as string }), ...words].join(' ');
  });

  async loadConfig(): Promise<void> {
    if (this.labels()) return;
    const config = await firstValueFrom(this.http.get<{ criteria: Criterion[]; labels: Labels }>('/api/config'));
    // A criterion without values yet (filled in the review page only) is left out of the form.
    this.criteria.set(config.criteria.filter(c => c.values.length));
    this.labels.set(config.labels);
  }

  setLang(lang: Lang): void {
    this.lang.set(lang);
    try { localStorage.setItem('clip-lang', lang); } catch { /* private mode: not remembered */ }
  }

  setTheme(theme: Theme): void {
    this.theme.set(theme);
    try { localStorage.setItem('clip-theme', theme); } catch { /* private mode: not remembered */ }
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

  private answerOf(name: string): string | null {
    const criterion = this.criteria().find(c => c.name === name);
    return criterion ? this.finalValue(criterion) : null;
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

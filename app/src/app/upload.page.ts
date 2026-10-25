import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AnalysisService } from './analysis.service';

/** Page 1: choose a photo (drag and drop, file picker or camera); it is sent for analysis at once. */
@Component({
  selector: 'app-upload-page',
  template: `
    <h1>{{ s.t('ui:upload_title') }}</h1>
    @if (busy()) {
      <div class="card busy">
        @if (s.photoUrl(); as url) { <img class="photo" [src]="url" alt=""> }
        <p class="center"><span class="spinner"></span> {{ s.t('ui:analysing') }}</p>
      </div>
    } @else {
      <div class="drop" [class.over]="over()"
           (dragover)="$event.preventDefault(); over.set(true)" (dragleave)="over.set(false)"
           (drop)="drop($event)">
        <p class="hint">{{ s.t('ui:drop_here') }}</p>
        <div class="buttons">
          <button type="button" class="main" (click)="camera.click()">📷 {{ s.t('ui:camera') }}</button>
          <button type="button" (click)="browse.click()">🖼 {{ s.t('ui:browse') }}</button>
        </div>
      </div>
      <!-- capture: the phone opens its camera directly; a computer falls back on the file picker. -->
      <input #camera type="file" accept="image/*" capture="environment" hidden (change)="picked($event)">
      <input #browse type="file" accept="image/*" hidden (change)="picked($event)">
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    }
  `,
})
export class UploadPage {
  protected s = inject(AnalysisService);
  private router = inject(Router);
  protected over = signal(false);
  protected busy = signal(false);
  protected error = signal<string | null>(null);

  protected drop(event: DragEvent): void {
    event.preventDefault();
    this.over.set(false);
    const file = event.dataTransfer?.files[0];
    if (file) this.send(file);
  }

  protected picked(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ''; // the same photo can be chosen again
    if (file) this.send(file);
  }

  private async send(file: File): Promise<void> {
    if (!file.type.startsWith('image/')) {
      this.error.set(this.s.t('ui:not_an_image'));
      return;
    }
    this.error.set(null);
    this.busy.set(true);
    try {
      await this.s.analyse(file);
      await this.router.navigate(['/review']);
    } catch {
      this.s.reset();
      this.error.set(this.s.t('ui:analysis_failed'));
    } finally {
      this.busy.set(false);
    }
  }
}

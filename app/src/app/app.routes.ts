import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { AnalysisService } from './analysis.service';
import { ReviewPage } from './review.page';
import { SummaryPage } from './summary.page';
import { UploadPage } from './upload.page';

// Without a photo being reviewed (page reloaded, back button after validating), go back to the upload page.
const reviewing = () => {
  const s = inject(AnalysisService);
  return (!!s.analysis() && !s.savedAs()) || inject(Router).parseUrl('/');
};
const validated = () => !!inject(AnalysisService).savedAs() || inject(Router).parseUrl('/');

export const routes: Routes = [
  { path: '', component: UploadPage },
  { path: 'review', component: ReviewPage, canActivate: [reviewing] },
  { path: 'summary', component: SummaryPage, canActivate: [validated] },
  { path: '**', redirectTo: '' },
];

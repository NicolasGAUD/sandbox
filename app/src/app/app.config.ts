import { provideHttpClient, withFetch } from '@angular/common/http';
import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withHashLocation } from '@angular/router';
import { AnalysisService } from './analysis.service';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Hash URLs (#/review): the server only serves static files, a reload never hits an unknown path.
    provideRouter(routes, withHashLocation()),
    provideHttpClient(withFetch()),
    // Criteria and labels are needed by every page.
    provideAppInitializer(() => inject(AnalysisService).loadConfig()),
  ],
};

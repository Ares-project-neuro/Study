import {pagesApi,vault} from './engine.js';
globalThis.NeuroStudyPages={api:pagesApi,vault};
// Initialize the static adapter before the shared interface calls boot().
import('../app/static/app.js');

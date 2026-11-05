import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.tsx';
import { createSource } from './source.ts';
import './styles.css';

createSource().then(src => {
  createRoot(document.getElementById('root')!).render(<StrictMode><App src={src} /></StrictMode>);
});

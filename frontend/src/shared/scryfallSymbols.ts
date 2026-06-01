import { ref } from 'vue';

import { listWorkspaceSymbols } from '@/shared/api';
import type { ScryfallSymbols } from '@/shared/api';

export const scryfallSymbols = ref<ScryfallSymbols>({});

let loadPromise: Promise<void> | null = null;

export async function loadScryfallSymbols(): Promise<void> {
  if (loadPromise === null) {
    loadPromise = listWorkspaceSymbols()
      .then((symbols) => {
        scryfallSymbols.value = symbols;
      })
      .catch(() => {
        scryfallSymbols.value = {};
      });
  }
  await loadPromise;
}

export async function reloadScryfallSymbols(): Promise<void> {
  loadPromise = null;
  await loadScryfallSymbols();
}

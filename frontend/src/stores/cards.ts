import { defineStore } from 'pinia';
import { ref } from 'vue';

import { type Card, getApiErrorMessage, searchCards } from '@/shared/api';

export const useCardsStore = defineStore('cards', () => {
  const search = ref('');
  const cards = ref<Card[]>([]);
  const selectedCard = ref<Card | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  let currentRequest = 0;

  async function runSearch(value = search.value): Promise<void> {
    search.value = value;
    const requestId = ++currentRequest;
    error.value = null;

    if (value.trim().length < 2) {
      cards.value = [];
      loading.value = false;
      return;
    }

    loading.value = true;
    try {
      const result = await searchCards(value);
      if (requestId === currentRequest) {
        cards.value = result;
      }
    } catch (caughtError) {
      if (requestId === currentRequest) {
        error.value = getApiErrorMessage(caughtError, 'Search is unavailable');
      }
    } finally {
      if (requestId === currentRequest) {
        loading.value = false;
      }
    }
  }

  function selectCard(card: Card): void {
    selectedCard.value = card;
  }

  return {
    search,
    cards,
    selectedCard,
    loading,
    error,
    runSearch,
    selectCard,
  };
});

import { computed, ref, watch } from 'vue';
import { defineStore } from 'pinia';

import {
  addDeckItem,
  createDeck,
  type Deck,
  type DeckCreate,
  type DeckItem,
  type DeckItemCreate,
  type DeckItemMove,
  type DeckItemUpdate,
  type DeckUpdate,
  deleteDeck,
  deleteDeckItem,
  getApiErrorMessage,
  listDeckItems,
  listDecks,
  moveDeckItem,
  updateDeck,
  updateDeckItem,
} from '@/shared/api';

const SELECTED_DECK_STORAGE_KEY = 'magic-explorer:selectedDeckId';

function readStoredDeckId(): number | null {
  const storedValue = window.localStorage.getItem(SELECTED_DECK_STORAGE_KEY);
  if (storedValue === null) {
    return null;
  }

  const parsedValue = Number(storedValue);
  return Number.isInteger(parsedValue) ? parsedValue : null;
}

export const useDecksStore = defineStore('decks', () => {
  const decks = ref<Deck[]>([]);
  const selectedDeckId = ref<number | null>(readStoredDeckId());
  const items = ref<DeckItem[]>([]);
  const decksLoading = ref(false);
  const itemsLoading = ref(false);
  const savingCollectionItemId = ref<number | null>(null);
  const savingDeck = ref(false);
  const error = ref<string | null>(null);

  const selectedDeck = computed(
    () => decks.value.find((deck) => deck.id === selectedDeckId.value) ?? null,
  );
  const totalCards = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));

  watch(selectedDeckId, (deckId) => {
    items.value = [];
    if (deckId === null) {
      window.localStorage.removeItem(SELECTED_DECK_STORAGE_KEY);
    } else {
      window.localStorage.setItem(SELECTED_DECK_STORAGE_KEY, String(deckId));
    }
  });

  async function fetchDecks(): Promise<void> {
    decksLoading.value = true;
    error.value = null;
    try {
      const fetchedDecks = await listDecks();
      decks.value = fetchedDecks;
      if (!fetchedDecks.some((deck) => deck.id === selectedDeckId.value)) {
        selectedDeckId.value = fetchedDecks[0]?.id ?? null;
      }
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Decks are unavailable');
    } finally {
      decksLoading.value = false;
    }
  }

  async function createNewDeck(payload: DeckCreate): Promise<boolean> {
    savingDeck.value = true;
    error.value = null;
    try {
      const deck = await createDeck(payload);
      decks.value = [...decks.value, deck];
      selectedDeckId.value = deck.id;
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not create deck');
      return false;
    } finally {
      savingDeck.value = false;
    }
  }

  async function updateSelectedDeck(payload: DeckUpdate): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    savingDeck.value = true;
    error.value = null;
    try {
      const updatedDeck = await updateDeck(selectedDeckId.value, payload);
      const deckIndex = decks.value.findIndex((deck) => deck.id === updatedDeck.id);
      if (deckIndex !== -1) {
        decks.value.splice(deckIndex, 1, updatedDeck);
      }
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not update deck');
      return false;
    } finally {
      savingDeck.value = false;
    }
  }

  async function removeSelectedDeck(): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    savingDeck.value = true;
    error.value = null;
    const removedDeckId = selectedDeckId.value;
    try {
      await deleteDeck(removedDeckId);
      decks.value = decks.value.filter((deck) => deck.id !== removedDeckId);
      selectedDeckId.value = decks.value[0]?.id ?? null;
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not delete deck');
      return false;
    } finally {
      savingDeck.value = false;
    }
  }

  async function fetchDeckItems(): Promise<void> {
    if (selectedDeckId.value === null) {
      await fetchDecks();
    }

    if (selectedDeckId.value === null) {
      items.value = [];
      return;
    }

    itemsLoading.value = true;
    error.value = null;
    try {
      items.value = await listDeckItems(selectedDeckId.value);
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Deck is unavailable');
    } finally {
      itemsLoading.value = false;
    }
  }

  async function addItem(payload: DeckItemCreate): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    savingCollectionItemId.value = payload.collection_item_id;
    error.value = null;
    try {
      const item = await addDeckItem(selectedDeckId.value, { quantity: 1, ...payload });
      const existingIndex = items.value.findIndex((existingItem) => existingItem.id === item.id);
      if (existingIndex === -1) {
        items.value = [...items.value, item];
      } else {
        items.value.splice(existingIndex, 1, item);
      }
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not add card to deck');
      return false;
    } finally {
      savingCollectionItemId.value = null;
    }
  }

  async function updateItem(itemId: number, payload: DeckItemUpdate): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    error.value = null;
    try {
      const item = await updateDeckItem(selectedDeckId.value, itemId, payload);
      const itemIndex = items.value.findIndex((existingItem) => existingItem.id === item.id);
      if (itemIndex !== -1) {
        items.value.splice(itemIndex, 1, item);
      }
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not update deck card');
      return false;
    }
  }

  async function removeItem(itemId: number): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    error.value = null;
    try {
      await deleteDeckItem(selectedDeckId.value, itemId);
      items.value = items.value.filter((item) => item.id !== itemId);
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not remove card from deck');
      return false;
    }
  }

  async function moveItem(itemId: number, payload: DeckItemMove): Promise<boolean> {
    if (selectedDeckId.value === null) {
      error.value = 'Select a deck first';
      return false;
    }

    error.value = null;
    try {
      await moveDeckItem(selectedDeckId.value, itemId, payload);
      await fetchDeckItems();
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not move deck card');
      return false;
    }
  }

  return {
    decks,
    selectedDeckId,
    selectedDeck,
    items,
    decksLoading,
    itemsLoading,
    savingCollectionItemId,
    savingDeck,
    error,
    totalCards,
    fetchDecks,
    fetchDeckItems,
    createNewDeck,
    updateSelectedDeck,
    removeSelectedDeck,
    addItem,
    updateItem,
    removeItem,
    moveItem,
  };
});

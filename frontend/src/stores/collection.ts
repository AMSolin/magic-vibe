import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import {
  addCollectionItem,
  type CollectionItem,
  deleteCollectionItem,
  listCollection,
} from '@/shared/api';

export const useCollectionStore = defineStore('collection', () => {
  const items = ref<CollectionItem[]>([]);
  const loading = ref(false);
  const savingCardId = ref<number | null>(null);
  const error = ref<string | null>(null);

  const totalCards = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));

  async function fetchCollection(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      items.value = await listCollection();
    } catch {
      error.value = 'Collection is unavailable';
    } finally {
      loading.value = false;
    }
  }

  async function addCard(cardId: number): Promise<void> {
    savingCardId.value = cardId;
    error.value = null;
    try {
      const item = await addCollectionItem(cardId);
      items.value = [item, ...items.value];
    } catch {
      error.value = 'Could not add card';
    } finally {
      savingCardId.value = null;
    }
  }

  async function removeItem(itemId: number): Promise<void> {
    const previousItems = items.value;
    items.value = items.value.filter((item) => item.id !== itemId);
    error.value = null;

    try {
      await deleteCollectionItem(itemId);
    } catch {
      items.value = previousItems;
      error.value = 'Could not remove card';
    }
  }

  return {
    items,
    loading,
    savingCardId,
    error,
    totalCards,
    fetchCollection,
    addCard,
    removeItem,
  };
});

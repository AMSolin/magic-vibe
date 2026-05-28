import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import {
  addCollectionItem,
  type CollectionItemCreate,
  type CollectionItem,
  deleteCollectionItem,
  listCollection,
  type CollectionItemUpdate,
  updateCollectionItem,
} from '@/shared/api';

export const useCollectionStore = defineStore('collection', () => {
  const items = ref<CollectionItem[]>([]);
  const loading = ref(false);
  const savingCardUuid = ref<string | null>(null);
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

  async function addCard(payload: CollectionItemCreate): Promise<void> {
    savingCardUuid.value = payload.card_uuid;
    error.value = null;
    try {
      const item = await addCollectionItem({ quantity: 1, ...payload });
      const existingIndex = items.value.findIndex((existingItem) => existingItem.id === item.id);
      if (existingIndex === -1) {
        items.value = [item, ...items.value];
      } else {
        items.value.splice(existingIndex, 1, item);
      }
    } catch {
      error.value = 'Could not add card';
    } finally {
      savingCardUuid.value = null;
    }
  }

  async function updateItem(itemId: number, payload: CollectionItemUpdate): Promise<void> {
    const previousItems = [...items.value];
    error.value = null;

    try {
      const item = await updateCollectionItem(itemId, payload);
      const itemIndex = items.value.findIndex((existingItem) => existingItem.id === item.id);
      if (itemIndex !== -1) {
        items.value.splice(itemIndex, 1, item);
      }
    } catch {
      items.value = previousItems;
      error.value = 'Could not update card';
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
    savingCardUuid,
    error,
    totalCards,
    fetchCollection,
    addCard,
    updateItem,
    removeItem,
  };
});

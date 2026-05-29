import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';

import {
  addCollectionItem,
  type Collection,
  type CollectionItem,
  type CollectionItemCreate,
  type CollectionItemUpdate,
  deleteCollectionItem,
  listCollectionItems,
  listCollections,
  updateCollectionItem,
} from '@/shared/api';

const SELECTED_COLLECTION_STORAGE_KEY = 'magic-explorer:selectedCollectionId';

function readStoredCollectionId(): number | null {
  const storedValue = window.localStorage.getItem(SELECTED_COLLECTION_STORAGE_KEY);
  if (storedValue === null) {
    return null;
  }

  const parsedValue = Number(storedValue);
  return Number.isInteger(parsedValue) ? parsedValue : null;
}

export const useCollectionStore = defineStore('collection', () => {
  const collections = ref<Collection[]>([]);
  const selectedCollectionId = ref<number | null>(readStoredCollectionId());
  const items = ref<CollectionItem[]>([]);
  const collectionsLoading = ref(false);
  const loading = ref(false);
  const savingCardUuid = ref<string | null>(null);
  const error = ref<string | null>(null);

  const selectedCollection = computed(
    () =>
      collections.value.find((collection) => collection.id === selectedCollectionId.value) ?? null,
  );
  const totalCards = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));

  watch(selectedCollectionId, (collectionId) => {
    items.value = [];
    if (collectionId === null) {
      window.localStorage.removeItem(SELECTED_COLLECTION_STORAGE_KEY);
    } else {
      window.localStorage.setItem(SELECTED_COLLECTION_STORAGE_KEY, String(collectionId));
    }
  });

  function chooseDefaultCollection(collectionList: Collection[]): number | null {
    return (
      collectionList.find((collection) => collection.is_default && !collection.is_wishlist)?.id ??
      collectionList.find((collection) => !collection.is_wishlist)?.id ??
      collectionList[0]?.id ??
      null
    );
  }

  function setSelectedCollection(collectionId: number | null): void {
    selectedCollectionId.value = collectionId;
  }

  async function fetchCollections(): Promise<void> {
    collectionsLoading.value = true;
    error.value = null;
    try {
      const fetchedCollections = await listCollections();
      collections.value = fetchedCollections;

      const selectedExists = fetchedCollections.some(
        (collection) => collection.id === selectedCollectionId.value,
      );
      if (!selectedExists) {
        setSelectedCollection(chooseDefaultCollection(fetchedCollections));
      }
    } catch {
      error.value = 'Collections are unavailable';
    } finally {
      collectionsLoading.value = false;
    }
  }

  async function fetchCollectionItems(): Promise<void> {
    if (selectedCollectionId.value === null) {
      await fetchCollections();
    }

    if (selectedCollectionId.value === null) {
      items.value = [];
      return;
    }

    loading.value = true;
    error.value = null;
    try {
      items.value = await listCollectionItems(selectedCollectionId.value);
    } catch {
      error.value = 'Collection is unavailable';
    } finally {
      loading.value = false;
    }
  }

  async function addCard(payload: CollectionItemCreate): Promise<void> {
    if (selectedCollectionId.value === null) {
      await fetchCollections();
    }

    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return;
    }

    savingCardUuid.value = payload.card_uuid;
    error.value = null;
    try {
      const item = await addCollectionItem(selectedCollectionId.value, { quantity: 1, ...payload });
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
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return;
    }

    const previousItems = [...items.value];
    error.value = null;

    try {
      const item = await updateCollectionItem(selectedCollectionId.value, itemId, payload);
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
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return;
    }

    const previousItems = items.value;
    items.value = items.value.filter((item) => item.id !== itemId);
    error.value = null;

    try {
      await deleteCollectionItem(selectedCollectionId.value, itemId);
    } catch {
      items.value = previousItems;
      error.value = 'Could not remove card';
    }
  }

  return {
    collections,
    selectedCollectionId,
    selectedCollection,
    items,
    collectionsLoading,
    loading,
    savingCardUuid,
    error,
    totalCards,
    fetchCollections,
    fetchCollectionItems,
    setSelectedCollection,
    addCard,
    updateItem,
    removeItem,
  };
});

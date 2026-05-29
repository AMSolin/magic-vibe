import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';

import {
  addCollectionItem,
  type Collection,
  type CollectionCreate,
  type CollectionItem,
  type CollectionItemCreate,
  type CollectionItemMove,
  type CollectionItemUpdate,
  type CollectionUpdate,
  createCollection,
  deleteCollection,
  deleteCollectionItem,
  listCollectionItems,
  listCollections,
  moveCollectionItem,
  updateCollection,
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
  const savingCollection = ref(false);
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

  async function createNewCollection(payload: CollectionCreate): Promise<boolean> {
    savingCollection.value = true;
    error.value = null;
    try {
      const collection = await createCollection(payload);
      collections.value = [...collections.value, collection];
      selectedCollectionId.value = collection.id;
      return true;
    } catch {
      error.value = 'Could not create collection';
      return false;
    } finally {
      savingCollection.value = false;
    }
  }

  async function updateSelectedCollection(payload: CollectionUpdate): Promise<boolean> {
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return false;
    }

    savingCollection.value = true;
    error.value = null;
    try {
      const updatedCollection = await updateCollection(selectedCollectionId.value, payload);
      const collectionIndex = collections.value.findIndex(
        (collection) => collection.id === updatedCollection.id,
      );
      if (collectionIndex !== -1) {
        collections.value.splice(collectionIndex, 1, updatedCollection);
      }
      return true;
    } catch {
      error.value = 'Could not update collection';
      return false;
    } finally {
      savingCollection.value = false;
    }
  }

  async function removeSelectedCollection(): Promise<boolean> {
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return false;
    }

    savingCollection.value = true;
    error.value = null;
    const removedCollectionId = selectedCollectionId.value;
    try {
      await deleteCollection(removedCollectionId);
      collections.value = collections.value.filter(
        (collection) => collection.id !== removedCollectionId,
      );
      setSelectedCollection(chooseDefaultCollection(collections.value));
      return true;
    } catch {
      error.value = 'Could not delete collection';
      return false;
    } finally {
      savingCollection.value = false;
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

  async function moveItem(itemId: number, payload: CollectionItemMove): Promise<boolean> {
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return false;
    }

    error.value = null;
    try {
      await moveCollectionItem(selectedCollectionId.value, itemId, payload);
      items.value = items.value.filter((item) => item.id !== itemId);
      return true;
    } catch {
      error.value = 'Could not move card';
      return false;
    }
  }

  return {
    collections,
    selectedCollectionId,
    selectedCollection,
    items,
    collectionsLoading,
    savingCollection,
    loading,
    savingCardUuid,
    error,
    totalCards,
    fetchCollections,
    fetchCollectionItems,
    createNewCollection,
    updateSelectedCollection,
    removeSelectedCollection,
    setSelectedCollection,
    addCard,
    updateItem,
    removeItem,
    moveItem,
  };
});

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
  getApiErrorMessage,
  listCollectionItemsPage,
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
  const itemPageFirst = ref(0);
  const itemPageRows = ref(100);
  const totalItems = ref(0);
  const totalCards = ref(0);
  const collectionsLoading = ref(false);
  const savingCollection = ref(false);
  const loading = ref(false);
  const savingCardUuid = ref<string | null>(null);
  const error = ref<string | null>(null);

  const selectedCollection = computed(
    () =>
      collections.value.find((collection) => collection.id === selectedCollectionId.value) ?? null,
  );
  watch(selectedCollectionId, (collectionId) => {
    items.value = [];
    itemPageFirst.value = 0;
    totalItems.value = 0;
    totalCards.value = 0;
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
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Collections are unavailable');
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
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not create collection');
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
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not update collection');
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
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not delete collection');
      return false;
    } finally {
      savingCollection.value = false;
    }
  }

  async function fetchCollectionItems(options?: { first?: number; rows?: number }): Promise<void> {
    if (selectedCollectionId.value === null) {
      await fetchCollections();
    }

    if (selectedCollectionId.value === null) {
      items.value = [];
      totalItems.value = 0;
      totalCards.value = 0;
      return;
    }

    if (options?.first !== undefined) {
      itemPageFirst.value = options.first;
    }
    if (options?.rows !== undefined) {
      itemPageRows.value = options.rows;
    }

    loading.value = true;
    error.value = null;
    try {
      const page = await listCollectionItemsPage(selectedCollectionId.value, {
        offset: itemPageFirst.value,
        limit: itemPageRows.value,
      });
      items.value = page.items;
      totalItems.value = page.total_count;
      totalCards.value = page.total_cards;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Collection is unavailable');
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
      totalCards.value += payload.quantity ?? 1;
      if (existingIndex === -1) {
        totalItems.value += 1;
        if (itemPageFirst.value === 0) {
          items.value = [item, ...items.value].slice(0, itemPageRows.value);
        }
      } else {
        items.value.splice(existingIndex, 1, item);
      }
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not add card');
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
      const previousItem = previousItems.find((existingItem) => existingItem.id === itemId);
      const item = await updateCollectionItem(selectedCollectionId.value, itemId, payload);
      const itemIndex = items.value.findIndex((existingItem) => existingItem.id === item.id);
      if (itemIndex !== -1) {
        items.value.splice(itemIndex, 1, item);
      }
      if (previousItem) {
        totalCards.value += item.quantity - previousItem.quantity;
      }
    } catch (caughtError) {
      items.value = previousItems;
      error.value = getApiErrorMessage(caughtError, 'Could not update card');
    }
  }

  async function removeItem(itemId: number): Promise<void> {
    if (selectedCollectionId.value === null) {
      error.value = 'Select a collection first';
      return;
    }

    const previousItems = items.value;
    const removedItem = previousItems.find((item) => item.id === itemId);
    items.value = items.value.filter((item) => item.id !== itemId);
    if (removedItem) {
      totalItems.value = Math.max(0, totalItems.value - 1);
      totalCards.value = Math.max(0, totalCards.value - removedItem.quantity);
    }
    error.value = null;

    try {
      await deleteCollectionItem(selectedCollectionId.value, itemId);
      if (selectedCollectionId.value !== null && items.value.length < itemPageRows.value) {
        await fetchCollectionItems();
      }
    } catch (caughtError) {
      items.value = previousItems;
      if (removedItem) {
        totalItems.value += 1;
        totalCards.value += removedItem.quantity;
      }
      error.value = getApiErrorMessage(caughtError, 'Could not remove card');
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
      const movedItem = items.value.find((item) => item.id === itemId);
      items.value = items.value.filter((item) => item.id !== itemId);
      if (movedItem) {
        totalItems.value = Math.max(0, totalItems.value - 1);
        totalCards.value = Math.max(0, totalCards.value - movedItem.quantity);
      }
      if (items.value.length < itemPageRows.value) {
        await fetchCollectionItems();
      }
      return true;
    } catch (caughtError) {
      error.value = getApiErrorMessage(caughtError, 'Could not move card');
      return false;
    }
  }

  return {
    collections,
    selectedCollectionId,
    selectedCollection,
    items,
    itemPageFirst,
    itemPageRows,
    totalItems,
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

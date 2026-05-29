<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dialog from 'primevue/dialog';
import InputNumber from 'primevue/inputnumber';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import ToggleSwitch from 'primevue/toggleswitch';

import type { Deck, DeckItem } from '@/shared/api';
import { useCollectionStore } from '@/stores/collection';
import { useDecksStore } from '@/stores/decks';

const SECTIONS = ['main', 'side', 'maybe', 'commander'];

const collectionStore = useCollectionStore();
const decksStore = useDecksStore();
const {
  collections,
  selectedCollectionId,
  items: collectionItems,
  collectionsLoading,
  loading: collectionLoading,
} = storeToRefs(collectionStore);
const {
  decks,
  selectedDeckId,
  selectedDeck,
  items: deckItems,
  decksLoading,
  itemsLoading,
  savingCollectionItemId,
  savingDeck,
  error,
  totalCards,
} = storeToRefs(decksStore);
const addSection = ref('main');
const moveTargets = ref<Record<number, string>>({});
const createDialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const newDeckName = ref('');
const newDeckIsDefault = ref(false);
const newDeckIsWishlist = ref(false);
const newDeckWishlistCollectionId = ref<number | null>(null);
const editName = ref('');
const editOwnerId = ref(1);
const editNote = ref('');
const editCreatedAt = ref('');
const editIsDefault = ref(false);
const editIsWishlist = ref(false);
const editWishlistCollectionId = ref<number | null>(null);

const wishlistCollections = computed(() =>
  collections.value.filter((collection) => collection.is_wishlist),
);
const compatibleCollections = computed(() => {
  if (selectedDeck.value?.is_wishlist) {
    return collections.value.filter(
      (collection) => collection.id === selectedDeck.value?.wishlist_collection_id,
    );
  }

  return collections.value.filter((collection) => !collection.is_wishlist);
});
const availableCollectionItems = computed(() =>
  collectionItems.value.filter((item) => item.available_quantity > 0),
);

function itemsForSection(section: string): DeckItem[] {
  return deckItems.value.filter((item) => item.section === section);
}

function quantityForSection(section: string): number {
  return itemsForSection(section).reduce((sum, item) => sum + item.quantity, 0);
}

function distinctForSection(section: string): number {
  return new Set(itemsForSection(section).map((item) => item.collection_item.card_uuid)).size;
}

function destinationOptions(section: string): string[] {
  return SECTIONS.filter((candidate) => candidate !== section);
}

function resetMetadata(deck: Deck | null): void {
  editName.value = deck?.name ?? '';
  editOwnerId.value = deck?.owner_id ?? 1;
  editNote.value = deck?.note ?? '';
  editCreatedAt.value = deck?.created_at.slice(0, 10) ?? '';
  editIsDefault.value = deck?.is_default ?? false;
  editIsWishlist.value = deck?.is_wishlist ?? false;
  editWishlistCollectionId.value = deck?.wishlist_collection_id ?? null;
}

async function syncCollectionForDeck(): Promise<void> {
  if (compatibleCollections.value.length === 0) {
    collectionStore.setSelectedCollection(null);
    return;
  }

  const selectedIsCompatible = compatibleCollections.value.some(
    (collection) => collection.id === selectedCollectionId.value,
  );
  if (!selectedIsCompatible) {
    collectionStore.setSelectedCollection(compatibleCollections.value[0]?.id ?? null);
  }

  await collectionStore.fetchCollectionItems();
}

async function refreshInventory(): Promise<void> {
  await collectionStore.fetchCollectionItems();
}

async function addToDeck(collectionItemId: number): Promise<void> {
  const added = await decksStore.addItem({
    collection_item_id: collectionItemId,
    section: addSection.value,
    is_commander: addSection.value === 'commander',
  });
  if (added) {
    await refreshInventory();
  }
}

async function updateDeckItem(itemId: number, quantity: number | null): Promise<void> {
  const updated = await decksStore.updateItem(itemId, { quantity: quantity ?? 1 });
  if (updated) {
    await refreshInventory();
  }
}

async function toggleCommander(item: DeckItem, value: boolean): Promise<void> {
  await decksStore.updateItem(item.id, { is_commander: value });
}

async function moveDeckItem(item: DeckItem, moveAll: boolean): Promise<void> {
  const section = moveTargets.value[item.id];
  if (!section) {
    return;
  }

  const moved = await decksStore.moveItem(item.id, {
    section,
    quantity: moveAll ? undefined : 1,
  });
  if (moved) {
    delete moveTargets.value[item.id];
    await refreshInventory();
  }
}

async function removeDeckItem(itemId: number): Promise<void> {
  const removed = await decksStore.removeItem(itemId);
  if (removed) {
    await refreshInventory();
  }
}

async function createNewDeck(): Promise<void> {
  const created = await decksStore.createNewDeck({
    name: newDeckName.value,
    is_default: newDeckIsDefault.value,
    is_wishlist: newDeckIsWishlist.value,
    wishlist_collection_id: newDeckIsWishlist.value
      ? newDeckWishlistCollectionId.value
      : null,
  });
  if (created) {
    createDialogVisible.value = false;
    newDeckName.value = '';
    newDeckIsDefault.value = false;
    newDeckIsWishlist.value = false;
    newDeckWishlistCollectionId.value = null;
  }
}

async function saveMetadata(): Promise<void> {
  await decksStore.updateSelectedDeck({
    name: editName.value,
    owner_id: editOwnerId.value,
    note: editNote.value || null,
    created_at: `${editCreatedAt.value}T00:00:00`,
    is_default: editIsDefault.value,
    is_wishlist: editIsWishlist.value,
    wishlist_collection_id: editIsWishlist.value ? editWishlistCollectionId.value : null,
  });
  await syncCollectionForDeck();
}

async function deleteSelectedDeck(): Promise<void> {
  const removed = await decksStore.removeSelectedDeck();
  if (removed) {
    deleteDialogVisible.value = false;
  }
}

onMounted(async () => {
  await Promise.all([collectionStore.fetchCollections(), decksStore.fetchDecks()]);
  await decksStore.fetchDeckItems();
  await syncCollectionForDeck();
});

watch(selectedDeck, (deck) => resetMetadata(deck), { immediate: true });

watch(selectedDeckId, async () => {
  await decksStore.fetchDeckItems();
  await syncCollectionForDeck();
});

watch(selectedCollectionId, async () => {
  await collectionStore.fetchCollectionItems();
});

watch(newDeckIsWishlist, (isWishlist) => {
  if (isWishlist && newDeckWishlistCollectionId.value === null) {
    newDeckWishlistCollectionId.value = wishlistCollections.value[0]?.id ?? null;
  }
});

watch(editIsWishlist, (isWishlist) => {
  if (isWishlist && editWishlistCollectionId.value === null) {
    editWishlistCollectionId.value = wishlistCollections.value[0]?.id ?? null;
  }
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>Decks</h1>
        <span class="summary">{{ selectedDeck?.name ?? 'No deck' }} · {{ totalCards }} cards</span>
      </div>
      <div class="header-actions">
        <Select
          v-model="selectedDeckId"
          class="collection-select"
          :options="decks"
          option-label="name"
          option-value="id"
          :loading="decksLoading"
          aria-label="Deck"
        />
        <Button icon="pi pi-plus" aria-label="Create deck" @click="createDialogVisible = true" />
        <Button
          icon="pi pi-trash"
          severity="secondary"
          aria-label="Delete deck"
          :disabled="decks.length <= 1"
          @click="deleteDialogVisible = true"
        />
      </div>
    </div>

    <p v-if="error" class="empty-state">{{ error }}</p>

    <section v-if="selectedDeck" class="tool-panel">
      <div class="section-header">
        <h2>Deck info</h2>
        <Button
          icon="pi pi-save"
          label="Save"
          size="small"
          :loading="savingDeck"
          @click="saveMetadata"
        />
      </div>
      <div class="metadata-grid">
        <label class="field">
          <span>Name</span>
          <InputText v-model="editName" />
        </label>
        <label class="field">
          <span>Owner ID</span>
          <InputNumber v-model="editOwnerId" :min="1" />
        </label>
        <label class="field">
          <span>Creation date</span>
          <InputText v-model="editCreatedAt" type="date" />
        </label>
        <label class="toggle-field">
          <Checkbox v-model="editIsDefault" binary />
          <span>Primary deck</span>
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="editIsWishlist" />
          <span>Wish deck</span>
        </label>
        <label v-if="editIsWishlist" class="field">
          <span>Wishlist collection</span>
          <Select
            v-model="editWishlistCollectionId"
            :options="wishlistCollections"
            option-label="name"
            option-value="id"
            aria-label="Wishlist collection"
          />
        </label>
        <label class="field note-field">
          <span>Note</span>
          <Textarea v-model="editNote" rows="2" auto-resize />
        </label>
      </div>
    </section>

    <section v-for="section in SECTIONS" :key="section" class="deck-section">
      <div class="section-title">
        <h2>{{ section }}</h2>
        <span>{{ quantityForSection(section) }} cards · {{ distinctForSection(section) }} distinct</span>
      </div>
      <DataTable
        v-if="itemsForSection(section).length > 0"
        :value="itemsForSection(section)"
        :loading="itemsLoading"
        data-key="id"
        striped-rows
      >
        <Column field="collection_item.card.name" header="Card" />
        <Column field="quantity" header="Qty">
          <template #body="{ data }">
            <InputNumber
              :model-value="data.quantity"
              input-class="quantity-input"
              :min="1"
              show-buttons
              @update:model-value="(value) => updateDeckItem(data.id, value)"
            />
          </template>
        </Column>
        <Column header="Cmdr">
          <template #body="{ data }">
            <Checkbox
              :model-value="data.is_commander"
              binary
              :aria-label="`Commander ${data.collection_item.card.name}`"
              @update:model-value="(value) => toggleCommander(data, value)"
            />
          </template>
        </Column>
        <Column field="collection_item.condition_code" header="Condition" />
        <Column header="Foil">
          <template #body="{ data }">
            {{ data.collection_item.foil ? 'Foil' : 'Nonfoil' }}
          </template>
        </Column>
        <Column header="Move">
          <template #body="{ data }">
            <div class="move-controls">
              <Select
                v-model="moveTargets[data.id]"
                class="move-select"
                :options="destinationOptions(data.section)"
                :aria-label="`Move ${data.collection_item.card.name}`"
                placeholder="Section"
              />
              <Button
                label="One"
                size="small"
                severity="secondary"
                :disabled="!moveTargets[data.id]"
                @click="moveDeckItem(data, false)"
              />
              <Button
                label="All"
                size="small"
                severity="secondary"
                :disabled="!moveTargets[data.id]"
                @click="moveDeckItem(data, true)"
              />
            </div>
          </template>
        </Column>
        <Column header="">
          <template #body="{ data }">
            <Button
              icon="pi pi-trash"
              severity="secondary"
              text
              rounded
              aria-label="Remove from deck"
              @click="removeDeckItem(data.id)"
            />
          </template>
        </Column>
      </DataTable>
      <p v-else class="empty-section">Empty</p>
    </section>

    <section class="deck-section">
      <div class="section-header">
        <h2>Add from collection</h2>
        <div class="add-defaults">
          <Select
            v-model="selectedCollectionId"
            class="collection-select"
            :options="compatibleCollections"
            option-label="name"
            option-value="id"
            :loading="collectionsLoading"
            aria-label="Source collection"
          />
          <Select v-model="addSection" :options="SECTIONS" aria-label="Deck section" />
        </div>
      </div>

      <DataTable
        :value="availableCollectionItems"
        :loading="collectionLoading"
        data-key="id"
        striped-rows
      >
        <Column field="card.name" header="Card" />
        <Column field="available_quantity" header="Available" />
        <Column field="quantity" header="Owned" />
        <Column field="condition_code" header="Condition" />
        <Column header="Foil">
          <template #body="{ data }">
            {{ data.foil ? 'Foil' : 'Nonfoil' }}
          </template>
        </Column>
        <Column header="">
          <template #body="{ data }">
            <Button
              icon="pi pi-plus"
              label="Add"
              size="small"
              :loading="savingCollectionItemId === data.id"
              @click="addToDeck(data.id)"
            />
          </template>
        </Column>
      </DataTable>
    </section>

    <Dialog v-model:visible="createDialogVisible" modal header="Create deck" class="deck-dialog">
      <div class="dialog-fields">
        <label class="field">
          <span>Name</span>
          <InputText v-model="newDeckName" autofocus />
        </label>
        <label class="toggle-field">
          <Checkbox v-model="newDeckIsDefault" binary />
          <span>Primary deck</span>
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="newDeckIsWishlist" />
          <span>Wish deck</span>
        </label>
        <label v-if="newDeckIsWishlist" class="field">
          <span>Wishlist collection</span>
          <Select
            v-model="newDeckWishlistCollectionId"
            :options="wishlistCollections"
            option-label="name"
            option-value="id"
            aria-label="New deck wishlist collection"
          />
        </label>
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="createDialogVisible = false" />
        <Button
          label="Create"
          icon="pi pi-plus"
          :loading="savingDeck"
          :disabled="!newDeckName.trim()"
          @click="createNewDeck"
        />
      </template>
    </Dialog>

    <Dialog v-model:visible="deleteDialogVisible" modal header="Delete deck" class="deck-dialog">
      <p>Delete {{ selectedDeck?.name }} and all cards assigned to it?</p>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="deleteDialogVisible = false" />
        <Button
          label="Delete"
          icon="pi pi-trash"
          severity="danger"
          :loading="savingDeck"
          @click="deleteSelectedDeck"
        />
      </template>
    </Dialog>
  </section>
</template>

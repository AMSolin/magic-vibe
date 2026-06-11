<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
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

import type { Collection } from '@/shared/api';
import { useCollectionStore } from '@/stores/collection';

const collectionStore = useCollectionStore();
const {
  collections,
  selectedCollectionId,
  selectedCollection,
  items,
  collectionsLoading,
  savingCollection,
  loading,
  error,
  totalCards,
  totalItems,
  itemPageFirst,
  itemPageRows,
} = storeToRefs(collectionStore);
const createDialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const newCollectionName = ref('');
const newCollectionIsDefault = ref(false);
const newCollectionIsWishlist = ref(false);
const editName = ref('');
const editOwnerId = ref(1);
const editNote = ref('');
const editCreatedAt = ref('');
const editIsDefault = ref(false);
const editIsWishlist = ref(false);
const moveTargets = ref<Record<number, number>>({});

function resetMetadata(collection: Collection | null): void {
  editName.value = collection?.name ?? '';
  editOwnerId.value = collection?.owner_id ?? 1;
  editNote.value = collection?.note ?? '';
  editCreatedAt.value = collection?.created_at.slice(0, 10) ?? '';
  editIsDefault.value = collection?.is_default ?? false;
  editIsWishlist.value = collection?.is_wishlist ?? false;
}

function targetCollections(collectionId: number): Collection[] {
  return collections.value.filter((collection) => collection.id !== collectionId);
}

async function createNewCollection(): Promise<void> {
  const created = await collectionStore.createNewCollection({
    name: newCollectionName.value,
    is_default: newCollectionIsDefault.value,
    is_wishlist: newCollectionIsWishlist.value,
  });
  if (created) {
    createDialogVisible.value = false;
    newCollectionName.value = '';
    newCollectionIsDefault.value = false;
    newCollectionIsWishlist.value = false;
  }
}

async function saveMetadata(): Promise<void> {
  await collectionStore.updateSelectedCollection({
    name: editName.value,
    owner_id: editOwnerId.value,
    note: editNote.value || null,
    created_at: `${editCreatedAt.value}T00:00:00`,
    is_default: editIsDefault.value,
    is_wishlist: editIsWishlist.value,
  });
}

async function deleteSelectedCollection(): Promise<void> {
  const removed = await collectionStore.removeSelectedCollection();
  if (removed) {
    deleteDialogVisible.value = false;
  }
}

async function moveItem(itemId: number): Promise<void> {
  const collectionId = moveTargets.value[itemId];
  if (!collectionId) {
    return;
  }

  const moved = await collectionStore.moveItem(itemId, { collection_id: collectionId });
  if (moved) {
    delete moveTargets.value[itemId];
  }
}

async function pageCollectionItems(event: { first: number; rows: number }): Promise<void> {
  await collectionStore.fetchCollectionItems({ first: event.first, rows: event.rows });
}

onMounted(async () => {
  await collectionStore.fetchCollections();
  await collectionStore.fetchCollectionItems();
});

watch(selectedCollection, (collection) => resetMetadata(collection), { immediate: true });

watch(selectedCollectionId, async () => {
  await collectionStore.fetchCollectionItems();
});

watch(editIsWishlist, (isWishlist) => {
  if (isWishlist) {
    editIsDefault.value = false;
  }
});

watch(newCollectionIsWishlist, (isWishlist) => {
  if (isWishlist) {
    newCollectionIsDefault.value = false;
  }
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>Collection</h1>
        <span class="summary">
          {{ selectedCollection?.name ?? 'No collection' }} · {{ totalCards }} cards
        </span>
      </div>
      <div class="header-actions">
        <Select
          v-model="selectedCollectionId"
          class="collection-select"
          :options="collections"
          option-label="name"
          option-value="id"
          :loading="collectionsLoading"
          aria-label="Collection"
        />
        <Button
          icon="pi pi-plus"
          aria-label="Create collection"
          @click="createDialogVisible = true"
        />
        <Button
          icon="pi pi-trash"
          severity="secondary"
          aria-label="Delete collection"
          :disabled="collections.length <= 1"
          @click="deleteDialogVisible = true"
        />
      </div>
    </div>

    <p v-if="error" class="empty-state">{{ error }}</p>

    <section v-if="selectedCollection" class="tool-panel">
      <div class="section-header">
        <h2>Collection info</h2>
        <Button
          icon="pi pi-save"
          label="Save"
          size="small"
          :loading="savingCollection"
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
          <Checkbox v-model="editIsDefault" binary :disabled="editIsWishlist" />
          <span>Primary collection</span>
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="editIsWishlist" />
          <span>Wishlist</span>
        </label>
        <label class="field note-field">
          <span>Note</span>
          <Textarea v-model="editNote" rows="2" auto-resize />
        </label>
      </div>
    </section>

    <DataTable
      :value="items"
      :loading="loading"
      data-key="id"
      striped-rows
      paginator
      lazy
      :first="itemPageFirst"
      :rows="itemPageRows"
      :total-records="totalItems"
      :rows-per-page-options="[50, 100, 250, 500]"
      paginator-template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown CurrentPageReport"
      current-page-report-template="{first}-{last} of {totalRecords}"
      @page="pageCollectionItems"
    >
      <template #empty>
        <p class="empty-state">Collection is empty</p>
      </template>
      <Column field="card.name" header="Card" />
      <Column field="card.type_line" header="Type" />
      <Column field="quantity" header="Owned">
        <template #body="{ data }">
          <InputNumber
            :model-value="data.quantity"
            input-class="quantity-input"
            :min="1"
            show-buttons
            @update:model-value="
              (value) => collectionStore.updateItem(data.id, { quantity: value ?? 1 })
            "
          />
        </template>
      </Column>
      <Column field="allocated_quantity" header="Allocated" />
      <Column field="available_quantity" header="Available" />
      <Column field="condition_code" header="Condition" />
      <Column header="Foil">
        <template #body="{ data }">
          {{ data.foil ? 'Foil' : 'Nonfoil' }}
        </template>
      </Column>
      <Column field="language" header="Language" />
      <Column header="Move">
        <template #body="{ data }">
          <div class="move-controls">
            <Select
              v-model="moveTargets[data.id]"
              class="move-select"
              :options="targetCollections(data.collection_id)"
              option-label="name"
              option-value="id"
              :aria-label="`Move ${data.card.name}`"
              placeholder="Collection"
              :disabled="data.allocated_quantity > 0"
            />
            <Button
              icon="pi pi-arrow-right"
              severity="secondary"
              size="small"
              :aria-label="`Move ${data.card.name} now`"
              :disabled="!moveTargets[data.id] || data.allocated_quantity > 0"
              @click="moveItem(data.id)"
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
            aria-label="Remove"
            :disabled="data.allocated_quantity > 0"
            @click="collectionStore.removeItem(data.id)"
          />
        </template>
      </Column>
    </DataTable>

    <Dialog
      v-model:visible="createDialogVisible"
      modal
      header="Create collection"
      class="deck-dialog"
    >
      <div class="dialog-fields">
        <label class="field">
          <span>Name</span>
          <InputText v-model="newCollectionName" autofocus />
        </label>
        <label class="toggle-field">
          <Checkbox v-model="newCollectionIsDefault" binary :disabled="newCollectionIsWishlist" />
          <span>Primary collection</span>
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="newCollectionIsWishlist" />
          <span>Wishlist</span>
        </label>
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="createDialogVisible = false" />
        <Button
          label="Create"
          icon="pi pi-plus"
          :loading="savingCollection"
          :disabled="!newCollectionName.trim()"
          @click="createNewCollection"
        />
      </template>
    </Dialog>

    <Dialog
      v-model:visible="deleteDialogVisible"
      modal
      header="Delete collection"
      class="deck-dialog"
    >
      <p>Delete {{ selectedCollection?.name }} and all cards stored in it?</p>
      <template #footer>
        <Button label="Cancel" severity="secondary" text @click="deleteDialogVisible = false" />
        <Button
          label="Delete"
          icon="pi pi-trash"
          severity="danger"
          :loading="savingCollection"
          @click="deleteSelectedCollection"
        />
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import InputNumber from 'primevue/inputnumber';
import Select from 'primevue/select';

import { useCollectionStore } from '@/stores/collection';

const collectionStore = useCollectionStore();
const {
  collections,
  selectedCollectionId,
  selectedCollection,
  items,
  collectionsLoading,
  loading,
  error,
  totalCards,
} = storeToRefs(collectionStore);

onMounted(async () => {
  await collectionStore.fetchCollections();
  await collectionStore.fetchCollectionItems();
});

watch(selectedCollectionId, async () => {
  await collectionStore.fetchCollectionItems();
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
      <Select
        v-model="selectedCollectionId"
        class="collection-select"
        :options="collections"
        option-label="name"
        option-value="id"
        :loading="collectionsLoading"
        aria-label="Collection"
      />
    </div>

    <p v-if="error" class="empty-state">{{ error }}</p>

    <DataTable :value="items" :loading="loading" data-key="id" striped-rows>
      <Column field="card.name" header="Card" />
      <Column field="quantity" header="Qty">
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
      <Column field="condition_code" header="Condition" />
      <Column header="Foil">
        <template #body="{ data }">
          {{ data.foil ? 'Foil' : 'Nonfoil' }}
        </template>
      </Column>
      <Column field="language" header="Language" />
      <Column header="">
        <template #body="{ data }">
          <Button
            icon="pi pi-trash"
            severity="secondary"
            text
            rounded
            aria-label="Remove"
            @click="collectionStore.removeItem(data.id)"
          />
        </template>
      </Column>
    </DataTable>
  </section>
</template>

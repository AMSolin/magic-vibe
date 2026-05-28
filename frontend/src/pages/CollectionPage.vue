<script setup lang="ts">
import { onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';

import { useCollectionStore } from '@/stores/collection';

const collectionStore = useCollectionStore();
const { items, loading, error, totalCards } = storeToRefs(collectionStore);

onMounted(async () => {
  await collectionStore.fetchCollection();
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1>Collection</h1>
      <span class="summary">{{ totalCards }} cards</span>
    </div>

    <p v-if="error" class="empty-state">{{ error }}</p>

    <DataTable :value="items" :loading="loading" data-key="id" striped-rows>
      <Column field="card.name" header="Card" />
      <Column field="quantity" header="Qty" />
      <Column field="finish" header="Finish" />
      <Column field="condition" header="Condition" />
      <Column field="location" header="Location" />
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

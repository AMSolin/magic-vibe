<script setup lang="ts">
import { watch } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import Card from 'primevue/card';
import InputText from 'primevue/inputtext';
import ProgressSpinner from 'primevue/progressspinner';

import { useCardsStore } from '@/stores/cards';
import { useCollectionStore } from '@/stores/collection';

const cardsStore = useCardsStore();
const collectionStore = useCollectionStore();
const { search, cards, loading, error } = storeToRefs(cardsStore);
const { savingCardId } = storeToRefs(collectionStore);

watch(
  search,
  (value) => cardsStore.runSearch(value),
  { immediate: true },
);
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1>Cards</h1>
      <InputText v-model="search" class="search-input" placeholder="Search cards" />
    </div>

    <ProgressSpinner v-if="loading" class="spinner" />
    <p v-else-if="error" class="empty-state">{{ error }}</p>
    <p v-else-if="search.length >= 2 && cards.length === 0" class="empty-state">No cards found</p>

    <div class="card-grid">
      <Card v-for="card in cards" :key="card.id" class="result-card">
        <template #header>
          <img v-if="card.image_normal" :src="card.image_normal" :alt="card.name" />
        </template>
        <template #title>{{ card.name }}</template>
        <template #subtitle>{{ card.type_line }}</template>
        <template #content>
          <p class="card-text">{{ card.oracle_text }}</p>
        </template>
        <template #footer>
          <Button
            icon="pi pi-plus"
            label="Add"
            size="small"
            :loading="savingCardId === card.id"
            @click="collectionStore.addCard(card.id)"
          />
        </template>
      </Card>
    </div>
  </section>
</template>

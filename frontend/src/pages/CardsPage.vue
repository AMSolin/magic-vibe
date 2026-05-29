<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import Card from 'primevue/card';
import Checkbox from 'primevue/checkbox';
import InputText from 'primevue/inputtext';
import ProgressSpinner from 'primevue/progressspinner';
import Select from 'primevue/select';

import { useCardsStore } from '@/stores/cards';
import { useCollectionStore } from '@/stores/collection';

const cardsStore = useCardsStore();
const collectionStore = useCollectionStore();
const { search, cards, loading, error } = storeToRefs(cardsStore);
const { collections, selectedCollectionId, collectionsLoading, savingCardUuid } =
  storeToRefs(collectionStore);
const conditions = ['NM', 'SP', 'MP', 'HP', 'D'];
const languages = ['English', 'Russian', 'Japanese'];
const addCondition = ref('NM');
const addLanguage = ref('English');
const addFoil = ref(false);

watch(
  search,
  (value) => cardsStore.runSearch(value),
  { immediate: true },
);

onMounted(async () => {
  await collectionStore.fetchCollections();
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <h1>Cards</h1>
      <InputText v-model="search" class="search-input" placeholder="Search cards" />
    </div>

    <div class="add-defaults">
      <Select
        v-model="selectedCollectionId"
        class="collection-select"
        :options="collections"
        option-label="name"
        option-value="id"
        size="small"
        :loading="collectionsLoading"
        aria-label="Collection"
      />
      <Select v-model="addCondition" :options="conditions" size="small" aria-label="Condition" />
      <Select v-model="addLanguage" :options="languages" size="small" aria-label="Language" />
      <label class="checkbox-label">
        <Checkbox v-model="addFoil" binary />
        <span>Foil</span>
      </label>
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
          <div class="add-card-controls">
            <Button
              icon="pi pi-plus"
              label="Add"
              size="small"
              :loading="savingCardUuid === card.card_uuid"
              @click="
                collectionStore.addCard({
                  card_uuid: card.card_uuid,
                  condition_code: addCondition,
                  foil: addFoil,
                  language: addLanguage,
                })
              "
            />
          </div>
        </template>
      </Card>
    </div>
  </section>
</template>

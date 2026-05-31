<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import InputNumber from 'primevue/inputnumber';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import ToggleSwitch from 'primevue/toggleswitch';

import {
  addWorkspaceCollectionItem,
  getApiErrorMessage,
  getWorkspacePrintingDetails,
  listWorkspaceCollectionItems,
  listWorkspaceCollections,
  listWorkspacePrintings,
  suggestWorkspaceCards,
} from '@/shared/api';
import type {
  CardDetails,
  CardPrinting,
  CardSuggestion,
  WorkspaceCollection,
  WorkspaceCollectionItem,
} from '@/shared/api';

type SetOption = {
  code: string;
  keyrune: string;
  name: string;
  releaseDate: number;
};

const conditions = ['NM', 'SP', 'MP', 'HP', 'D'];
const sidebarCollapsed = ref(false);
const activeTab = ref<'info' | 'add'>('add');
const collections = ref<WorkspaceCollection[]>([]);
const selectedCollectionId = ref<number | null>(null);
const inventory = ref<WorkspaceCollectionItem[]>([]);
const search = ref('');
const exactMatch = ref(false);
const suggestions = ref<CardSuggestion[]>([]);
const suggestionsOpen = ref(false);
const selectedAlias = ref<CardSuggestion | null>(null);
const printings = ref<CardPrinting[]>([]);
const selectedSetCode = ref('');
const languageCode = ref('');
const cardNumber = ref('');
const finishId = ref<number | null>(null);
const condition = ref('NM');
const quantity = ref(1);
const details = ref<CardDetails | null>(null);
const loadingDetails = ref(false);
const saving = ref(false);
const message = ref('');
const error = ref('');
const imageDialog = ref<HTMLDialogElement | null>(null);
const searchContainer = ref<HTMLElement | null>(null);
const selectedFaceOrder = ref(0);
let suggestTimer: number | undefined;
let suppressNextSuggestionRefresh = false;

const selectedCollection = computed(
  () => collections.value.find((collection) => collection.id === selectedCollectionId.value) ?? null,
);
const totalCards = computed(() => inventory.value.reduce((sum, item) => sum + item.quantity, 0));
const sets = computed<SetOption[]>(() => {
  const uniqueSets = new Map<string, SetOption>();
  for (const printing of printings.value) {
    if (!uniqueSets.has(printing.set_code)) {
      uniqueSets.set(printing.set_code, {
        code: printing.set_code,
        keyrune: printing.keyrune_code.toLocaleLowerCase(),
        name: printing.set_name,
        releaseDate: printing.release_date,
      });
    }
  }
  return [...uniqueSets.values()].sort((left, right) => right.releaseDate - left.releaseDate);
});
const selectedSet = computed(() => sets.value.find((set) => set.code === selectedSetCode.value));
const setPrintings = computed(() =>
  printings.value.filter((printing) => printing.set_code === selectedSetCode.value),
);
const languages = computed(() => {
  const uniqueLanguages = new Map<string, string>();
  for (const printing of setPrintings.value) {
    uniqueLanguages.set(printing.language_code, printing.language);
  }
  return [...uniqueLanguages.entries()].map(([code, name]) => ({ code, name }));
});
const languagePrintings = computed(() =>
  setPrintings.value.filter((printing) => printing.language_code === languageCode.value),
);
const numbers = computed(() => [...new Set(languagePrintings.value.map((printing) => printing.collector_number))]);
const selectedPrinting = computed(
  () =>
    languagePrintings.value.find((printing) => printing.collector_number === cardNumber.value) ??
    null,
);
const finishes = computed(() => selectedPrinting.value?.finishes ?? []);
const cardFaces = computed(() => details.value?.card.card_faces ?? []);
const selectedFace = computed(() => cardFaces.value[selectedFaceOrder.value] ?? details.value?.card);
const cardName = computed(() => selectedFace.value?.printed_name ?? selectedFace.value?.name ?? '');
const cardText = computed(() => selectedFace.value?.printed_text ?? selectedFace.value?.oracle_text ?? '');
const cardType = computed(() => selectedFace.value?.printed_type_line ?? selectedFace.value?.type_line ?? '');
const imageNormalUrl = computed(() =>
  details.value?.image_normal_url ? `${details.value.image_normal_url}?face_order=${selectedFaceOrder.value}` : '',
);
const imageNativeUrl = computed(() =>
  details.value?.image_native_url ? `${details.value.image_native_url}?face_order=${selectedFaceOrder.value}` : '',
);

function usePrintingDefaults(preferredLanguageCode?: string): void {
  const firstSet = sets.value[0];
  if (!firstSet) {
    return;
  }
  selectedSetCode.value = firstSet.code;
  selectSet(firstSet, preferredLanguageCode);
}

function selectSet(set: SetOption, preferredLanguageCode?: string): void {
  selectedSetCode.value = set.code;
  const availableLanguages = new Set(
    printings.value
      .filter((printing) => printing.set_code === set.code)
      .map((printing) => printing.language_code),
  );
  languageCode.value =
    (preferredLanguageCode && availableLanguages.has(preferredLanguageCode)
      ? preferredLanguageCode
      : languages.value[0]?.code) ?? '';
  cardNumber.value = numbers.value[0] ?? '';
  finishId.value = finishes.value[0]?.id ?? null;
}

async function chooseSuggestion(suggestion: CardSuggestion): Promise<void> {
  selectedAlias.value = suggestion;
  suppressNextSuggestionRefresh = search.value !== suggestion.name;
  search.value = suggestion.name;
  suggestions.value = [];
  suggestionsOpen.value = false;
  error.value = '';
  try {
    const options = await listWorkspacePrintings(suggestion.oracle_id, suggestion.language_code);
    printings.value = options.printings;
    usePrintingDefaults(options.preferred_language_code);
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Printing options are unavailable');
  }
}

function updateSearch(value: string | undefined): void {
  search.value = value ?? '';
  suggestionsOpen.value = true;
}

function cancelSearchDraft(): void {
  if (suggestTimer !== undefined) {
    window.clearTimeout(suggestTimer);
  }
  const confirmedName = selectedAlias.value?.name ?? '';
  suppressNextSuggestionRefresh = search.value !== confirmedName;
  search.value = confirmedName;
  suggestions.value = [];
  suggestionsOpen.value = false;
}

function reopenSuggestions(): void {
  if (search.value.trim()) {
    suggestionsOpen.value = true;
    void refreshSuggestions();
  }
}

function handleDocumentClick(event: MouseEvent): void {
  if (!searchContainer.value?.contains(event.target as Node)) {
    cancelSearchDraft();
  }
}

async function refreshSuggestions(): Promise<void> {
  if (!search.value.trim()) {
    suggestions.value = [];
    return;
  }
  try {
    suggestions.value = await suggestWorkspaceCards(search.value.trim(), exactMatch.value);
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card search is unavailable');
  }
}

async function refreshDetails(): Promise<void> {
  if (!selectedPrinting.value) {
    details.value = null;
    return;
  }
  loadingDetails.value = true;
  selectedFaceOrder.value = 0;
  error.value = '';
  try {
    details.value = await getWorkspacePrintingDetails(selectedPrinting.value.id);
  } catch (requestError) {
    details.value = null;
    error.value = getApiErrorMessage(requestError, 'Card preview is unavailable');
  } finally {
    loadingDetails.value = false;
  }
}

async function refreshInventory(): Promise<void> {
  if (selectedCollectionId.value === null) {
    inventory.value = [];
    return;
  }
  try {
    inventory.value = await listWorkspaceCollectionItems(selectedCollectionId.value);
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Collection items are unavailable');
  }
}

async function addCard(): Promise<void> {
  if (selectedCollectionId.value === null || !selectedPrinting.value || finishId.value === null) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await addWorkspaceCollectionItem(selectedCollectionId.value, {
      printing_id: selectedPrinting.value.id,
      finish_id: finishId.value,
      condition_code: condition.value,
      quantity: quantity.value,
    });
    await refreshInventory();
    message.value = `Added to ${selectedCollection.value?.name ?? 'collection'}`;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card could not be added');
  } finally {
    saving.value = false;
  }
}

function openImageDialog(): void {
  if (imageNativeUrl.value) {
    imageDialog.value?.showModal();
  }
}

watch([search, exactMatch], () => {
  if (suggestTimer !== undefined) {
    window.clearTimeout(suggestTimer);
  }
  if (suppressNextSuggestionRefresh) {
    suppressNextSuggestionRefresh = false;
    return;
  }
  suggestTimer = window.setTimeout(refreshSuggestions, 180);
});

watch(selectedCollectionId, refreshInventory);

watch(languageCode, () => {
  cardNumber.value = numbers.value.includes(cardNumber.value) ? cardNumber.value : (numbers.value[0] ?? '');
});

watch(selectedPrinting, () => {
  finishId.value = finishes.value.some((finish) => finish.id === finishId.value)
    ? finishId.value
    : (finishes.value[0]?.id ?? null);
  void refreshDetails();
});

onMounted(async () => {
  document.addEventListener('click', handleDocumentClick);
  collections.value = await listWorkspaceCollections();
  selectedCollectionId.value =
    collections.value.find((collection) => collection.is_default)?.id ?? collections.value[0]?.id ?? null;
});

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick);
});
</script>

<template>
  <section class="collection-workspace">
    <aside class="collection-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <Button
        icon="pi pi-bars"
        severity="secondary"
        text
        :aria-label="sidebarCollapsed ? 'Expand collections' : 'Collapse collections'"
        @click="sidebarCollapsed = !sidebarCollapsed"
      />
      <template v-if="!sidebarCollapsed">
        <h2>Collections</h2>
        <div class="sidebar-list">
          <button
            v-for="collection in collections"
            :key="collection.id"
            type="button"
            :class="{ selected: selectedCollectionId === collection.id }"
            @click="selectedCollectionId = collection.id"
          >
            <span>{{ collection.name }}</span>
            <i v-if="selectedCollectionId === collection.id" class="pi pi-check" />
          </button>
        </div>
        <div class="sidebar-actions">
          <Button icon="pi pi-plus" label="Add" size="small" />
          <Button icon="pi pi-pencil" label="Rename" size="small" severity="secondary" />
          <Button icon="pi pi-trash" label="Delete" size="small" severity="secondary" />
        </div>
      </template>
    </aside>

    <main class="inventory-pane">
      <div class="workspace-heading">
        <h1>{{ selectedCollection?.name ?? 'Collection' }}</h1>
        <p>{{ totalCards }} cards in collection</p>
      </div>
      <div class="inventory-table">
        <div class="inventory-row inventory-header">
          <span>Qty</span><span>Name</span><span>Type</span><span>Set</span><span>Cost</span>
        </div>
        <div v-for="item in inventory" :key="item.id" class="inventory-row">
          <strong>{{ item.quantity }}</strong>
          <span>{{ item.name }}</span>
          <span>{{ item.type }}</span>
          <span>{{ item.set_code }}</span>
          <span>{{ item.mana_cost || '—' }}</span>
        </div>
      </div>
    </main>

    <aside class="inspector-pane">
      <div class="inspector-tabs">
        <Button label="Collection info" :severity="activeTab === 'info' ? undefined : 'secondary'" @click="activeTab = 'info'" />
        <Button label="Add cards" :severity="activeTab === 'add' ? undefined : 'secondary'" @click="activeTab = 'add'" />
      </div>

      <p v-if="error" class="empty-state">{{ error }}</p>

      <section v-if="activeTab === 'info'" class="inspector-content">
        <h2>Collection info</h2>
        <label class="field"><span>Name</span><InputText :model-value="selectedCollection?.name" /></label>
        <label class="field"><span>Owner</span><Select model-value="Player" :options="['Player']" /></label>
        <label class="field"><span>Created at</span><InputText :model-value="String(selectedCollection?.created_at ?? '')" /></label>
        <label class="toggle-field"><Checkbox :model-value="selectedCollection?.is_default" binary /><span>Primary collection</span></label>
        <label class="toggle-field"><ToggleSwitch :model-value="selectedCollection?.is_wishlist" /><span>Wishlist</span></label>
        <label class="field"><span>Note</span><Textarea :model-value="selectedCollection?.note ?? ''" rows="4" /></label>
      </section>

      <section v-else class="inspector-content add-card-inspector">
        <div class="card-search-row">
          <div ref="searchContainer" class="search-with-suggestions">
            <label class="field">
              <span>Card name</span>
              <span class="search-input-wrap">
                <InputText
                  :model-value="search"
                  placeholder="Start typing a card name"
                  @focus="reopenSuggestions"
                  @keydown.esc.prevent="cancelSearchDraft"
                  @update:model-value="updateSearch"
                />
                <Button
                  v-if="suggestionsOpen"
                  icon="pi pi-times"
                  severity="secondary"
                  text
                  aria-label="Cancel card search"
                  @click="cancelSearchDraft"
                />
              </span>
            </label>
            <div v-if="suggestionsOpen && suggestions.length" class="suggestions">
              <button v-for="suggestion in suggestions" :key="`${suggestion.oracle_id}-${suggestion.face_order}-${suggestion.language_code}-${suggestion.name}`" type="button" @click="chooseSuggestion(suggestion)">
                {{ suggestion.name }} ({{ suggestion.language }})
              </button>
            </div>
          </div>
          <label class="toggle-field"><Checkbox v-model="exactMatch" binary /><span>Exact match</span></label>
        </div>

        <template v-if="selectedAlias && selectedPrinting">
          <div class="card-config-layout">
            <div class="card-image-wrap">
              <div class="selected-alias">{{ cardName }} ({{ selectedAlias.language }})</div>
              <button type="button" class="card-image-button" aria-label="View card image at native resolution" :disabled="!imageNativeUrl" @click="openImageDialog">
                <img v-if="imageNormalUrl" :src="imageNormalUrl" :alt="cardName" />
                <span v-else>{{ loadingDetails ? 'Loading image…' : 'Image unavailable' }}</span>
              </button>
              <div class="card-rules-text">
                <strong>{{ cardType }}</strong>
                <span>{{ cardText }}</span>
              </div>
              <div v-if="cardFaces.length > 1" class="number-toggle-group card-face-toggle">
                <button
                  v-for="(face, faceOrder) in cardFaces"
                  :key="`${faceOrder}-${face.name}`"
                  type="button"
                  :class="{ selected: selectedFaceOrder === faceOrder }"
                  @click="selectedFaceOrder = faceOrder"
                >
                  {{ face.printed_name ?? face.name ?? `Side ${faceOrder + 1}` }}
                </button>
              </div>
            </div>

            <div class="card-attributes">
              <div class="field">
                <span>Set</span>
                <div class="set-icon-grid">
                  <button v-for="set in sets" :key="set.code" type="button" :aria-label="set.name" :class="{ selected: selectedSetCode === set.code }" @click="selectSet(set, languageCode)">
                    <i :class="`ss ss-${set.keyrune} ss-2x`" />
                  </button>
                </div>
                <strong class="selected-set-name">{{ selectedSet?.name }}</strong>
              </div>
              <label class="field">
                <span>Language</span>
                <Select v-model="languageCode" :options="languages" option-label="name" option-value="code" />
              </label>
              <div class="field">
                <span>Card number</span>
                <div class="number-toggle-group">
                  <button v-for="number in numbers" :key="number" type="button" :class="{ selected: cardNumber === number }" @click="cardNumber = number">{{ number }}</button>
                </div>
              </div>
              <label class="field">
                <span>Finish</span>
                <Select v-model="finishId" :options="finishes" option-label="name" option-value="id" />
              </label>
              <div class="compact-field-row">
                <label class="field"><span>Condition</span><Select v-model="condition" :options="conditions" /></label>
                <label class="field"><span>Quantity</span><InputNumber v-model="quantity" :min="1" show-buttons /></label>
              </div>
              <div class="panel-actions">
                <span v-if="message" class="success-text">{{ message }}</span>
                <Button icon="pi pi-plus" label="Add to collection" :loading="saving" @click="addCard" />
              </div>
            </div>
          </div>
        </template>
      </section>
    </aside>

    <dialog ref="imageDialog" class="card-image-dialog" @click.self="imageDialog?.close()">
      <Button icon="pi pi-times" severity="secondary" text aria-label="Close full-size card image" @click="imageDialog?.close()" />
      <img v-if="imageNativeUrl" :src="imageNativeUrl" alt="Selected card at native resolution" />
    </dialog>
  </section>
</template>

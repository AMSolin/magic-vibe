<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import DatePicker from 'primevue/datepicker';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import ToggleSwitch from 'primevue/toggleswitch';

import {
  addWorkspaceDeckItem,
  createWorkspaceDeck,
  deleteWorkspaceDeck,
  deleteWorkspaceDeckItem,
  getApiErrorMessage,
  listWorkspaceDeckItems,
  listWorkspaceDecks,
  listWorkspacePlayers,
  searchWorkspaceDeckInventory,
  updateWorkspaceDeckItem,
  updateWorkspaceDeck,
} from '@/shared/api';
import type {
  WorkspaceDeck,
  WorkspaceDeckInventoryItem,
  WorkspaceDeckInventorySearchResult,
  WorkspaceDeckItem,
  WorkspacePlayer,
} from '@/shared/api';

const SECTIONS = ['main', 'side', 'maybe', 'commander'] as const;
const HOVER_PREVIEW_DELAY_MS = 450;

type PreviewCandidate = {
  printing_id: number;
  release_date: number;
  language_code: string;
  name: string;
};

type DeckSectionRow = {
  key: string;
  name: string;
  oracle_id: string;
  quantity: number;
  previewCandidate: PreviewCandidate | null;
  items: WorkspaceDeckItem[];
};

const sidebarCollapsed = ref(false);
const decks = ref<WorkspaceDeck[]>([]);
const players = ref<WorkspacePlayer[]>([]);
const deckItems = ref<WorkspaceDeckItem[]>([]);
const searchResults = ref<WorkspaceDeckInventorySearchResult[]>([]);
const expandedOracleIds = ref<Set<string>>(new Set());
const expandedDecklistRowKeys = ref<Set<string>>(new Set());
const addingItemIds = ref<Set<number>>(new Set());
const editingDeckItemIds = ref<Set<number>>(new Set());
const openMoveMenuItemId = ref<number | null>(null);
const moveMenuDirection = ref<'up' | 'down'>('down');
const highlightedDecklistRow = ref<{ section: string; oracleId: string } | null>(null);
const selectedDeckId = ref<number | null>(null);
const searchQuery = ref('');
const oracleSearchContext = ref<{ oracleId: string; name: string } | null>(null);
const createDialogVisible = ref(false);
const editDialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const saving = ref(false);
const loading = ref(false);
const searchLoading = ref(false);
const hoverPreview = ref<{
  imageUrl: string;
  fallbackImageUrl: string | null;
  label: string;
  x: number;
  y: number;
} | null>(null);
const hoverPreviewLoading = ref(false);
const hoverPreviewError = ref(false);
const message = ref('');
const error = ref('');
const createError = ref('');
const editError = ref('');
let searchRequestId = 0;
let hoverPreviewTimer: number | null = null;
let hoverPreviewRequestId = 0;
let decklistHighlightTimer: number | null = null;

const draftName = ref('');
const draftPlayerId = ref<number | null>(null);
const draftCreatedAt = ref<Date | null>(null);
const draftNote = ref('');
const draftIsWish = ref(false);

const selectedDeck = computed(
  () => decks.value.find((deck) => deck.id === selectedDeckId.value) ?? null,
);
const preferredPlayer = computed(() => players.value.find((player) => player.is_default) ?? null);
const ownerOptions = computed(() => [
  { id: null, name: 'No owner' },
  ...players.value.map((player) => ({ id: player.id, name: player.name })),
]);
const visibleSections = computed(() =>
  ['commander', 'main', 'side', 'maybe'].filter(
    (section) => section === 'main' || rowsForSection(section).length > 0,
  ),
);
const searchResultCount = computed(() =>
  searchResults.value.reduce((sum, result) => sum + result.items.length, 0),
);
const hasSearchContext = computed(() =>
  Boolean(searchQuery.value.trim() || oracleSearchContext.value),
);
const hoverPreviewStyle = computed(() => {
  if (!hoverPreview.value) {
    return {};
  }
  const previewWidth = 220;
  const previewHeight = 306;
  const gap = 14;
  const viewportPadding = 12;
  const preferredLeft = hoverPreview.value.x + gap;
  const preferredTop = hoverPreview.value.y + gap;
  const maxLeft = Math.max(viewportPadding, window.innerWidth - previewWidth - viewportPadding);
  const maxTop = Math.max(viewportPadding, window.innerHeight - previewHeight - viewportPadding);
  const left =
    preferredLeft + previewWidth <= maxLeft + previewWidth
      ? preferredLeft
      : hoverPreview.value.x - previewWidth - gap;
  const top =
    preferredTop + previewHeight <= maxTop + previewHeight
      ? preferredTop
      : hoverPreview.value.y - previewHeight - gap;
  return {
    left: `${Math.min(Math.max(viewportPadding, left), maxLeft)}px`,
    top: `${Math.min(Math.max(viewportPadding, top), maxTop)}px`,
  };
});

function rowsForSection(section: string): DeckSectionRow[] {
  const rows = new Map<string, DeckSectionRow>();
  for (const item of deckItems.value.filter((deckItem) => deckItem.section === section)) {
    const groupKey = item.oracle_id || `${item.id}`;
    const row = rows.get(groupKey);
    if (row) {
      row.quantity += item.quantity;
      row.items.push(item);
      row.previewCandidate = choosePreviewCandidate(
        [
          ...(row.previewCandidate ? [row.previewCandidate] : []),
          deckItemPreviewCandidate(item),
        ].filter((candidate): candidate is PreviewCandidate => candidate !== null),
      );
    } else {
      rows.set(groupKey, {
        key: `${section}:${groupKey}`,
        name: item.name,
        oracle_id: item.oracle_id,
        quantity: item.quantity,
        previewCandidate: deckItemPreviewCandidate(item),
        items: [item],
      });
    }
  }
  return [...rows.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function currentDecklistRowKeys(): Set<string> {
  return new Set(
    deckItems.value.map((item) => `${item.section}:${item.oracle_id || item.id}`),
  );
}

function isDecklistRowExpanded(key: string): boolean {
  return expandedDecklistRowKeys.value.has(key);
}

function isDecklistRowHighlighted(section: string, row: DeckSectionRow): boolean {
  return (
    highlightedDecklistRow.value?.section === section &&
    highlightedDecklistRow.value.oracleId === row.oracle_id
  );
}

function toggleDecklistRow(key: string): void {
  const nextExpanded = new Set(expandedDecklistRowKeys.value);
  if (nextExpanded.has(key)) {
    nextExpanded.delete(key);
  } else {
    nextExpanded.add(key);
  }
  expandedDecklistRowKeys.value = nextExpanded;
}

function highlightDecklistRow(section: string, oracleId: string): void {
  if (decklistHighlightTimer !== null) {
    window.clearTimeout(decklistHighlightTimer);
  }
  highlightedDecklistRow.value = { section, oracleId };
  decklistHighlightTimer = window.setTimeout(() => {
    highlightedDecklistRow.value = null;
    decklistHighlightTimer = null;
  }, 2200);
}

function deckItemDetails(item: WorkspaceDeckItem): string {
  return [
    item.collection_name,
    item.set_code ? `${item.set_code.toUpperCase()} #${item.collector_number ?? ''}` : null,
    item.language,
    item.finish,
    item.condition_code,
  ]
    .filter((part): part is string => Boolean(part))
    .join(' / ');
}

function deckItemPreviewCandidate(item: WorkspaceDeckItem): PreviewCandidate | null {
  if (
    item.printing_id === null ||
    item.release_date === null ||
    item.language_code === null
  ) {
    return null;
  }
  return {
    printing_id: item.printing_id,
    release_date: item.release_date,
    language_code: item.language_code,
    name: item.name,
  };
}

function inventoryItemPreviewCandidate(item: WorkspaceDeckInventoryItem): PreviewCandidate {
  return {
    printing_id: item.printing_id,
    release_date: item.release_date,
    language_code: item.language_code,
    name: item.name,
  };
}

function languagePriority(languageCode: string, preferredLanguageCode?: string): number {
  if (preferredLanguageCode && languageCode === preferredLanguageCode) {
    return -1;
  }
  if (languageCode === 'en') {
    return 0;
  }
  if (languageCode === 'ru') {
    return 1;
  }
  return 3;
}

function choosePreviewCandidate(
  candidates: PreviewCandidate[],
  preferredLanguageCode?: string,
): PreviewCandidate | null {
  return [...candidates].sort((left, right) => {
    if (right.release_date !== left.release_date) {
      return right.release_date - left.release_date;
    }
    return (
      languagePriority(left.language_code, preferredLanguageCode) -
      languagePriority(right.language_code, preferredLanguageCode)
    );
  })[0] ?? null;
}

function searchResultPreviewCandidate(
  result: WorkspaceDeckInventorySearchResult,
): PreviewCandidate | null {
  return choosePreviewCandidate(
    result.items.map(inventoryItemPreviewCandidate),
    result.language_code,
  );
}

function imageUrl(candidate: PreviewCandidate, preferredLanguageCode?: string): string {
  const languageCode = preferredLanguageCode || candidate.language_code;
  const params = new URLSearchParams({
    language_code: languageCode,
    preview_request: String(++hoverPreviewRequestId),
  });
  return `/api/workspace/printings/${candidate.printing_id}/images/normal?${params.toString()}`;
}

function updateHoverPreviewPosition(event: MouseEvent): void {
  if (!hoverPreview.value) {
    return;
  }
  hoverPreview.value = {
    ...hoverPreview.value,
    x: event.clientX,
    y: event.clientY,
  };
}

function clearHoverPreviewTimer(): void {
  if (hoverPreviewTimer !== null) {
    window.clearTimeout(hoverPreviewTimer);
    hoverPreviewTimer = null;
  }
}

function startHoverPreview(
  event: MouseEvent,
  candidate: PreviewCandidate | null,
  preferredLanguageCode?: string,
): void {
  clearHoverPreviewTimer();
  hoverPreview.value = null;
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
  if (
    event.target instanceof Element &&
    event.target.closest('.decklist-detail-actions')
  ) {
    return;
  }
  if (!candidate) {
    return;
  }
  const { clientX, clientY } = event;
  const initialImageUrl = imageUrl(candidate, preferredLanguageCode);
  const fallbackImageUrl =
    (preferredLanguageCode || candidate.language_code) === 'en' ? null : imageUrl(candidate, 'en');
  hoverPreviewTimer = window.setTimeout(() => {
    hoverPreview.value = {
      imageUrl: initialImageUrl,
      fallbackImageUrl,
      label: candidate.name,
      x: clientX,
      y: clientY,
    };
    hoverPreviewLoading.value = true;
  }, HOVER_PREVIEW_DELAY_MS);
}

function stopHoverPreview(): void {
  clearHoverPreviewTimer();
  hoverPreview.value = null;
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
}

function stopHoverPreviewIfLeaving(event: MouseEvent): void {
  const currentTarget = event.currentTarget;
  const relatedTarget = event.relatedTarget;
  if (
    currentTarget instanceof Element &&
    relatedTarget instanceof Node &&
    currentTarget.contains(relatedTarget)
  ) {
    return;
  }
  stopHoverPreview();
}

function handleHoverPreviewLoad(): void {
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
}

function handleHoverPreviewError(): void {
  if (
    hoverPreview.value?.fallbackImageUrl &&
    hoverPreview.value.imageUrl !== hoverPreview.value.fallbackImageUrl
  ) {
    hoverPreview.value = {
      ...hoverPreview.value,
      imageUrl: hoverPreview.value.fallbackImageUrl,
    };
    hoverPreviewLoading.value = true;
    hoverPreviewError.value = false;
    return;
  }
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = true;
}

function isOracleExpanded(oracleId: string): boolean {
  return expandedOracleIds.value.has(oracleId);
}

function toggleOracle(oracleId: string): void {
  const nextExpanded = new Set(expandedOracleIds.value);
  if (nextExpanded.has(oracleId)) {
    nextExpanded.delete(oracleId);
  } else {
    nextExpanded.add(oracleId);
  }
  expandedOracleIds.value = nextExpanded;
}

function isAddingItem(itemId: number): boolean {
  return addingItemIds.value.has(itemId);
}

function isEditingDeckItem(itemId: number): boolean {
  return editingDeckItemIds.value.has(itemId);
}

function moveTargetSections(currentSection: string): string[] {
  return SECTIONS.filter((section) => section !== currentSection);
}

function moveTargetLabel(section: string): string {
  if (section === 'side') {
    return 'Move to Sideboard:';
  }
  if (section === 'maybe') {
    return 'Move to Maybeboard:';
  }
  if (section === 'commander') {
    return 'Move to Commander:';
  }
  return 'Move to Main:';
}

function sectionLabel(section: string): string {
  if (section === 'side') {
    return 'Sideboard';
  }
  if (section === 'maybe') {
    return 'Maybeboard';
  }
  if (section === 'commander') {
    return 'Commander';
  }
  return 'Main';
}

function toggleMoveMenu(event: MouseEvent, itemId: number): void {
  if (openMoveMenuItemId.value === itemId) {
    openMoveMenuItemId.value = null;
    return;
  }
  const currentTarget = event.currentTarget;
  if (currentTarget instanceof Element) {
    const rect = currentTarget.getBoundingClientRect();
    moveMenuDirection.value = window.innerHeight - rect.bottom < 190 ? 'up' : 'down';
  } else {
    moveMenuDirection.value = 'down';
  }
  openMoveMenuItemId.value = itemId;
}

function formatAllocation(item: WorkspaceDeckInventoryItem): string {
  if (item.allocations.length === 0) {
    return 'No deck allocations';
  }
  return item.allocations
    .map((allocation) => `${allocation.deck_name} / ${allocation.section}: ${allocation.quantity}`)
    .join('; ');
}

function timestampToDate(timestamp: number | null | undefined): Date | null {
  return typeof timestamp === 'number' ? new Date(timestamp * 1000) : null;
}

function dateToTimestamp(date: Date | null): number | null {
  return date ? Math.floor(date.getTime() / 1000) : null;
}

function resetDraft(deck: WorkspaceDeck | null = null): void {
  draftName.value = deck?.name ?? '';
  draftPlayerId.value = deck?.player_id ?? preferredPlayer.value?.id ?? null;
  draftCreatedAt.value = timestampToDate(deck?.created_at ?? Math.floor(Date.now() / 1000));
  draftNote.value = deck?.note ?? '';
  draftIsWish.value = deck?.is_wish ?? false;
}

function openCreateDeckDialog(): void {
  resetDraft();
  draftIsWish.value = false;
  createError.value = '';
  createDialogVisible.value = true;
}

function openEditDeckDialog(): void {
  if (!selectedDeck.value) {
    return;
  }
  resetDraft(selectedDeck.value);
  editError.value = '';
  editDialogVisible.value = true;
}

function selectDeck(deckId: number): void {
  selectedDeckId.value = deckId;
  message.value = '';
  error.value = '';
  searchQuery.value = '';
  oracleSearchContext.value = null;
  searchResults.value = [];
  expandedOracleIds.value = new Set();
  expandedDecklistRowKeys.value = new Set();
}

async function refreshDecks(preferredDeckId?: number): Promise<void> {
  decks.value = await listWorkspaceDecks();
  selectedDeckId.value =
    preferredDeckId ??
    (selectedDeckId.value && decks.value.some((deck) => deck.id === selectedDeckId.value)
      ? selectedDeckId.value
      : decks.value[0]?.id ?? null);
}

async function refreshDeckItems(): Promise<void> {
  if (selectedDeckId.value === null) {
    deckItems.value = [];
    expandedDecklistRowKeys.value = new Set();
    return;
  }
  deckItems.value = await listWorkspaceDeckItems(selectedDeckId.value);
  const currentKeys = currentDecklistRowKeys();
  expandedDecklistRowKeys.value = new Set(
    [...expandedDecklistRowKeys.value].filter((key) => currentKeys.has(key)),
  );
}

async function refreshSearchResults(): Promise<void> {
  const deck = selectedDeck.value;
  const query = searchQuery.value.trim();
  const oracleId = oracleSearchContext.value?.oracleId;
  const requestId = ++searchRequestId;
  if (!deck || deck.is_wish || (!query && !oracleId)) {
    searchResults.value = [];
    searchLoading.value = false;
    return;
  }
  searchLoading.value = true;
  try {
    const results = await searchWorkspaceDeckInventory(deck.id, query, oracleId);
    if (requestId === searchRequestId) {
      searchResults.value = results;
      if (oracleId) {
        expandedOracleIds.value = new Set(results.map((result) => result.oracle_id));
      }
    }
  } catch (requestError) {
    if (requestId === searchRequestId) {
      error.value = getApiErrorMessage(requestError, 'Deck inventory search is unavailable');
      searchResults.value = [];
    }
  } finally {
    if (requestId === searchRequestId) {
      searchLoading.value = false;
    }
  }
}

function clearOracleSearchContext(): void {
  oracleSearchContext.value = null;
}

function searchDecklistOracle(row: DeckSectionRow): void {
  const deck = selectedDeck.value;
  if (!deck || deck.is_wish) {
    return;
  }
  error.value = '';
  message.value = '';
  oracleSearchContext.value = {
    oracleId: row.oracle_id,
    name: row.name,
  };
  searchQuery.value = row.name;
  expandedOracleIds.value = new Set([row.oracle_id]);
  void refreshSearchResults();
}

async function refreshAll(preferredDeckId?: number): Promise<void> {
  loading.value = true;
  error.value = '';
  try {
    players.value = await listWorkspacePlayers();
    await refreshDecks(preferredDeckId);
    await refreshDeckItems();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Decks are unavailable');
  } finally {
    loading.value = false;
  }
}

async function createDeck(): Promise<void> {
  const createdAt = dateToTimestamp(draftCreatedAt.value);
  if (!draftName.value.trim() || createdAt === null) {
    return;
  }
  saving.value = true;
  createError.value = '';
  error.value = '';
  message.value = '';
  try {
    const created = await createWorkspaceDeck({
      name: draftName.value.trim(),
      player_id: draftPlayerId.value,
      note: draftNote.value || null,
      is_wish: draftIsWish.value,
      created_at: createdAt,
    });
    createDialogVisible.value = false;
    await refreshAll(created.id);
    message.value = 'Deck created';
  } catch (requestError) {
    createError.value = getApiErrorMessage(requestError, 'Deck could not be created');
  } finally {
    saving.value = false;
  }
}

async function saveDeckMetadata(): Promise<void> {
  const deck = selectedDeck.value;
  const createdAt = dateToTimestamp(draftCreatedAt.value);
  if (!deck || !draftName.value.trim() || createdAt === null) {
    return;
  }
  saving.value = true;
  editError.value = '';
  error.value = '';
  message.value = '';
  try {
    const updated = await updateWorkspaceDeck(deck.id, {
      name: draftName.value.trim(),
      player_id: draftPlayerId.value,
      note: draftNote.value || null,
      created_at: createdAt,
    });
    editDialogVisible.value = false;
    await refreshAll(updated.id);
    message.value = 'Deck changes saved';
  } catch (requestError) {
    editError.value = getApiErrorMessage(requestError, 'Deck changes could not be saved');
  } finally {
    saving.value = false;
  }
}

async function confirmDeleteDeck(): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspaceDeck(deck.id);
    deleteDialogVisible.value = false;
    await refreshAll();
    message.value = 'Deck deleted';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Deck could not be deleted');
  } finally {
    saving.value = false;
  }
}

async function addInventoryItemToDeck(item: WorkspaceDeckInventoryItem): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck || item.available_quantity <= 0) {
    return;
  }
  const nextAdding = new Set(addingItemIds.value);
  nextAdding.add(item.collection_item_id);
  addingItemIds.value = nextAdding;
  error.value = '';
  message.value = '';
  try {
    const addedItem = await addWorkspaceDeckItem(deck.id, {
      collection_item_id: item.collection_item_id,
      section: 'main',
      quantity: 1,
    });
    await refreshDeckItems();
    await refreshSearchResults();
    highlightDecklistRow(addedItem.section, addedItem.oracle_id);
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card could not be added to deck');
  } finally {
    const remainingAdding = new Set(addingItemIds.value);
    remainingAdding.delete(item.collection_item_id);
    addingItemIds.value = remainingAdding;
  }
}

async function runDeckItemEdit(
  item: WorkspaceDeckItem,
  action: () => Promise<unknown>,
  fallbackMessage: string,
): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck) {
    return;
  }
  const nextEditing = new Set(editingDeckItemIds.value);
  nextEditing.add(item.id);
  editingDeckItemIds.value = nextEditing;
  error.value = '';
  message.value = '';
  try {
    await action();
    await refreshDeckItems();
    await refreshSearchResults();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, fallbackMessage);
  } finally {
    const remainingEditing = new Set(editingDeckItemIds.value);
    remainingEditing.delete(item.id);
    editingDeckItemIds.value = remainingEditing;
  }
}

async function decrementDeckItem(item: WorkspaceDeckItem): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck) {
    return;
  }
  await runDeckItemEdit(
    item,
    () =>
      item.quantity <= 1
        ? deleteWorkspaceDeckItem(deck.id, item.id)
        : updateWorkspaceDeckItem(deck.id, item.id, { quantity: item.quantity - 1 }),
    'Card quantity could not be updated',
  );
}

async function removeDeckItem(item: WorkspaceDeckItem): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck) {
    return;
  }
  await runDeckItemEdit(
    item,
    () => deleteWorkspaceDeckItem(deck.id, item.id),
    'Card could not be removed from deck',
  );
}

async function moveDeckItemCopiesToSection(
  item: WorkspaceDeckItem,
  section: string,
  quantity: number,
): Promise<void> {
  const deck = selectedDeck.value;
  if (!deck || section === item.section) {
    return;
  }
  openMoveMenuItemId.value = null;
  await runDeckItemEdit(
    item,
    () => updateWorkspaceDeckItem(deck.id, item.id, { section, quantity }),
    'Card could not be moved',
  );
}

watch(selectedDeckId, async () => {
  try {
    await refreshDeckItems();
    await refreshSearchResults();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Deck contents are unavailable');
  }
});

watch([searchQuery, selectedDeck], () => {
  window.setTimeout(() => {
    void refreshSearchResults();
  }, 250);
});

onMounted(() => {
  void refreshAll();
});

onBeforeUnmount(() => {
  clearHoverPreviewTimer();
  if (decklistHighlightTimer !== null) {
    window.clearTimeout(decklistHighlightTimer);
  }
});
</script>

<template>
  <section class="collection-workspace decks-workspace" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <aside class="collection-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <Button
        icon="pi pi-bars"
        severity="secondary"
        text
        :aria-label="sidebarCollapsed ? 'Expand decks' : 'Collapse decks'"
        @click="sidebarCollapsed = !sidebarCollapsed"
      />
      <template v-if="!sidebarCollapsed">
        <h2>Decks</h2>
        <div class="sidebar-list">
          <button
            v-for="deck in decks"
            :key="deck.id"
            type="button"
            :class="{ selected: selectedDeckId === deck.id }"
            @click="selectDeck(deck.id)"
          >
            <span>{{ deck.name }}</span>
            <i v-if="deck.is_wish" class="pi pi-heart-fill" title="Wish deck" />
          </button>
        </div>
        <div class="sidebar-actions">
          <Button icon="pi pi-plus" label="Add" size="small" @click="openCreateDeckDialog" />
          <Button
            icon="pi pi-pencil"
            label="Edit"
            size="small"
            severity="secondary"
            :disabled="!selectedDeck"
            @click="openEditDeckDialog"
          />
          <Button
            icon="pi pi-trash"
            label="Delete"
            size="small"
            severity="danger"
            :disabled="!selectedDeck"
            @click="deleteDialogVisible = true"
          />
        </div>
      </template>
    </aside>

    <main class="inventory-pane deck-search-pane">
      <div class="deck-tabs" role="tablist" aria-label="Deck workspace">
        <button type="button" class="active" role="tab" aria-selected="true">Search cards</button>
      </div>

      <section class="deck-tab-panel" role="tabpanel">
        <p v-if="message" class="success-text">{{ message }}</p>
        <p v-if="error" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ error }}</span>
        </p>

        <section class="deck-search-filters">
          <label class="field">
            <span>Card name</span>
            <InputText v-model="searchQuery" placeholder="Search by name" @input="clearOracleSearchContext" />
          </label>
        </section>

        <section class="deck-search-results">
          <div class="section-header">
            <h2>Search results</h2>
            <span>{{ searchResultCount }}</span>
          </div>
          <p v-if="selectedDeck?.is_wish" class="empty-state">
            Wish deck search will be added after physical allocation.
          </p>
          <p v-else-if="!selectedDeck" class="empty-state">Create or select a physical deck.</p>
          <p v-else-if="!hasSearchContext" class="empty-state">Search owned cards by name.</p>
          <p v-else-if="!searchResults.length && !searchLoading" class="empty-state">
            No owned physical cards match this search.
          </p>
          <div v-else class="deck-search-list">
            <article v-for="result in searchResults" :key="result.oracle_id" class="deck-search-result">
            <button
              type="button"
              class="deck-result-summary"
              @pointerenter="startHoverPreview($event, searchResultPreviewCandidate(result), result.language_code)"
              @pointermove="updateHoverPreviewPosition"
              @pointerleave="stopHoverPreview"
              @mouseenter="startHoverPreview($event, searchResultPreviewCandidate(result), result.language_code)"
              @mousemove="updateHoverPreviewPosition"
              @mouseleave="stopHoverPreview"
              @mouseover="startHoverPreview($event, searchResultPreviewCandidate(result), result.language_code)"
              @mouseout="stopHoverPreviewIfLeaving"
              @click="toggleOracle(result.oracle_id)"
            >
              <i
                :class="isOracleExpanded(result.oracle_id) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"
                aria-hidden="true"
              />
              <span>{{ result.name }}</span>
              <strong>{{ result.total_available }} / {{ result.total_owned }}</strong>
            </button>
            <div v-if="isOracleExpanded(result.oracle_id)" class="deck-result-items">
              <div
                v-for="item in result.items"
                :key="item.collection_item_id"
                class="deck-result-item"
                :class="{ unavailable: item.available_quantity <= 0 }"
                :data-collection-item-id="item.collection_item_id"
                @pointerenter="startHoverPreview($event, inventoryItemPreviewCandidate(item), result.language_code)"
                @pointermove="updateHoverPreviewPosition"
                @pointerleave="stopHoverPreview"
                @mouseenter="startHoverPreview($event, inventoryItemPreviewCandidate(item), result.language_code)"
                @mousemove="updateHoverPreviewPosition"
                @mouseleave="stopHoverPreview"
                @mouseover="startHoverPreview($event, inventoryItemPreviewCandidate(item), result.language_code)"
                @mouseout="stopHoverPreviewIfLeaving"
              >
                <div class="deck-result-item-main">
                  <strong>{{ item.name }}</strong>
                  <span>
                    {{ item.collection_name }} / {{ item.set_code.toUpperCase() }}
                    #{{ item.collector_number }} / {{ item.language }} /
                    {{ item.finish }} / {{ item.condition_code }}
                  </span>
                  <small>{{ formatAllocation(item) }}</small>
                </div>
                <div class="deck-result-item-actions">
                  <span>{{ item.available_quantity }} / {{ item.owned_quantity }}</span>
                  <Button
                    icon="pi pi-plus"
                    size="small"
                    rounded
                    :aria-label="`Add ${item.name}`"
                    :disabled="item.available_quantity <= 0 || isAddingItem(item.collection_item_id)"
                    :loading="isAddingItem(item.collection_item_id)"
                    @click="addInventoryItemToDeck(item)"
                  />
                </div>
              </div>
            </div>
            </article>
          </div>
        </section>
      </section>
    </main>

    <aside class="inspector-pane deck-contents-pane">
      <div class="workspace-heading">
        <h1>{{ selectedDeck?.name ?? 'Deck contents' }}</h1>
      </div>
      <section v-if="selectedDeck" class="inspector-content deck-list-content">
        <section v-for="section in visibleSections" :key="section" class="decklist-section">
          <div class="section-header">
            <h2>{{ sectionLabel(section) }}</h2>
            <strong class="decklist-section-count">
              {{ rowsForSection(section).reduce((sum, item) => sum + item.quantity, 0) }}
            </strong>
          </div>
          <div v-if="rowsForSection(section).length" class="decklist">
            <div v-for="item in rowsForSection(section)" :key="item.key" class="decklist-row-group">
              <div
                class="decklist-row decklist-summary-row"
                :class="{ highlighted: isDecklistRowHighlighted(section, item) }"
                @pointerenter="startHoverPreview($event, item.previewCandidate)"
                @pointermove="updateHoverPreviewPosition"
                @pointerleave="stopHoverPreview"
                @mouseenter="startHoverPreview($event, item.previewCandidate)"
                @mousemove="updateHoverPreviewPosition"
                @mouseleave="stopHoverPreview"
                @mouseover="startHoverPreview($event, item.previewCandidate)"
                @mouseout="stopHoverPreviewIfLeaving"
              >
                <button
                  type="button"
                  class="decklist-summary-toggle"
                  @click="toggleDecklistRow(item.key)"
                >
                  <i
                    :class="isDecklistRowExpanded(item.key) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"
                    aria-hidden="true"
                  />
                  <span>{{ item.name }}</span>
                </button>
                <Button
                  icon="pi pi-plus"
                  size="small"
                  rounded
                  text
                  :aria-label="`Find available copies of ${item.name}`"
                  @click="searchDecklistOracle(item)"
                />
                <strong>{{ item.quantity }}</strong>
              </div>
              <div v-if="isDecklistRowExpanded(item.key)" class="decklist-detail-list">
                <div
                  v-for="deckItem in item.items"
                  :key="deckItem.id"
                  class="decklist-detail-row"
                  @pointerenter="startHoverPreview($event, deckItemPreviewCandidate(deckItem))"
                  @pointermove="updateHoverPreviewPosition"
                  @pointerleave="stopHoverPreview"
                  @mouseenter="startHoverPreview($event, deckItemPreviewCandidate(deckItem))"
                  @mousemove="updateHoverPreviewPosition"
                  @mouseleave="stopHoverPreview"
                  @mouseover="startHoverPreview($event, deckItemPreviewCandidate(deckItem))"
                  @mouseout="stopHoverPreviewIfLeaving"
                >
                  <div>
                    <strong>{{ deckItem.name }}</strong>
                    <span>{{ deckItemDetails(deckItem) }}</span>
                  </div>
                  <span class="decklist-detail-quantity">{{ deckItem.quantity }}</span>
                  <div
                    class="decklist-detail-actions"
                    @pointerenter="stopHoverPreview"
                    @mouseenter="stopHoverPreview"
                    @mouseover.stop
                  >
                    <Button
                      icon="pi pi-arrow-right"
                      size="small"
                      rounded
                      text
                      :aria-label="`Move ${deckItem.name}`"
                      title="Move cards"
                      :disabled="isEditingDeckItem(deckItem.id)"
                      @click.stop="toggleMoveMenu($event, deckItem.id)"
                    />
                    <Button
                      icon="pi pi-minus"
                      size="small"
                      rounded
                      text
                      :aria-label="`Remove one ${deckItem.name}`"
                      title="Remove one card"
                      :disabled="isEditingDeckItem(deckItem.id)"
                      :loading="isEditingDeckItem(deckItem.id)"
                      @click="decrementDeckItem(deckItem)"
                    />
                    <Button
                      icon="pi pi-trash"
                      size="small"
                      rounded
                      text
                      severity="danger"
                      :aria-label="`Remove all ${deckItem.name}`"
                      title="Remove all cards"
                      :disabled="isEditingDeckItem(deckItem.id)"
                      @click="removeDeckItem(deckItem)"
                    />
                  </div>
                  <div
                    v-if="openMoveMenuItemId === deckItem.id"
                    class="decklist-move-menu"
                    :class="{ 'opens-up': moveMenuDirection === 'up' }"
                    role="menu"
                  >
                    <div
                      v-for="targetSection in moveTargetSections(deckItem.section)"
                      :key="targetSection"
                      class="decklist-move-menu-row"
                    >
                      <span>{{ moveTargetLabel(targetSection) }}</span>
                      <button
                        type="button"
                        title="Move one card"
                        @click="moveDeckItemCopiesToSection(deckItem, targetSection, 1)"
                      >
                        One card
                      </button>
                      <button
                        v-if="deckItem.quantity > 1"
                        type="button"
                        :title="`Move all ${deckItem.quantity} cards`"
                        @click="moveDeckItemCopiesToSection(deckItem, targetSection, deckItem.quantity)"
                      >
                        All {{ deckItem.quantity }} cards
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="empty-state">No cards yet.</p>
        </section>
      </section>
      <p v-else class="empty-state">Create a deck to start building.</p>
    </aside>

    <Dialog v-model:visible="createDialogVisible" modal header="Create deck">
      <div class="dialog-fields deck-dialog-fields">
        <label class="field"><span>Name</span><InputText v-model="draftName" autofocus /></label>
        <label class="field">
          <span>Owner</span>
          <Select v-model="draftPlayerId" :options="ownerOptions" option-label="name" option-value="id" />
        </label>
        <label class="field">
          <span>Created at</span>
          <DatePicker v-model="draftCreatedAt" date-format="yy-mm-dd" show-icon />
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="draftIsWish" />
          <span>Wish deck</span>
        </label>
        <label class="field">
          <span>Note</span>
          <Textarea v-model="draftNote" rows="3" auto-resize />
        </label>
        <p v-if="createError" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ createError }}</span>
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="createDialogVisible = false" />
          <Button
            icon="pi pi-plus"
            label="Create deck"
            :disabled="!draftName.trim() || !draftCreatedAt"
            :loading="saving"
            @click="createDeck"
          />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:visible="editDialogVisible" modal header="Edit deck">
      <div class="dialog-fields deck-dialog-fields">
        <label class="field"><span>Name</span><InputText v-model="draftName" autofocus /></label>
        <label class="field">
          <span>Owner</span>
          <Select v-model="draftPlayerId" :options="ownerOptions" option-label="name" option-value="id" />
        </label>
        <label class="field">
          <span>Created at</span>
          <DatePicker v-model="draftCreatedAt" date-format="yy-mm-dd" show-icon />
        </label>
        <label class="toggle-field">
          <ToggleSwitch :model-value="draftIsWish" disabled />
          <span>Wish deck</span>
        </label>
        <label class="field">
          <span>Note</span>
          <Textarea v-model="draftNote" rows="3" auto-resize />
        </label>
        <p v-if="editError" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ editError }}</span>
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="editDialogVisible = false" />
          <Button
            icon="pi pi-save"
            label="Save changes"
            :disabled="!draftName.trim() || !draftCreatedAt"
            :loading="saving"
            @click="saveDeckMetadata"
          />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:visible="deleteDialogVisible" modal header="Delete deck">
      <div class="dialog-fields">
        <p class="warning-text">
          Delete {{ selectedDeck?.name }}? Its deck contents will be removed.
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="deleteDialogVisible = false" />
          <Button
            icon="pi pi-trash"
            label="Delete deck"
            severity="danger"
            :loading="saving"
            @click="confirmDeleteDeck"
          />
        </div>
      </template>
    </Dialog>

    <div
      v-if="hoverPreview"
      class="deck-hover-preview"
      :style="hoverPreviewStyle"
      role="status"
      aria-live="polite"
    >
      <img
        v-if="!hoverPreviewError"
        :key="hoverPreview.imageUrl"
        :src="hoverPreview.imageUrl"
        :alt="hoverPreview.label"
        :class="{ 'loading-image': hoverPreviewLoading }"
        @load="handleHoverPreviewLoad"
        @error="handleHoverPreviewError"
      />
      <span v-if="hoverPreviewLoading" class="card-image-loading-overlay">Loading image</span>
      <span v-else-if="hoverPreviewError" class="deck-hover-preview-error">
        Image unavailable
      </span>
    </div>
  </section>
</template>

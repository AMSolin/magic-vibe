<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import DatePicker from 'primevue/datepicker';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import ToggleSwitch from 'primevue/toggleswitch';

import {
  createWorkspaceDeck,
  deleteWorkspaceDeck,
  getApiErrorMessage,
  listWorkspaceDeckItems,
  listWorkspaceDecks,
  listWorkspacePlayers,
  updateWorkspaceDeck,
} from '@/shared/api';
import type { WorkspaceDeck, WorkspaceDeckItem, WorkspacePlayer } from '@/shared/api';

const SECTIONS = ['main', 'side', 'maybe', 'commander'] as const;

const sidebarCollapsed = ref(false);
const decks = ref<WorkspaceDeck[]>([]);
const players = ref<WorkspacePlayer[]>([]);
const deckItems = ref<WorkspaceDeckItem[]>([]);
const selectedDeckId = ref<number | null>(null);
const searchQuery = ref('');
const addSection = ref('main');
const createDialogVisible = ref(false);
const editDialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const saving = ref(false);
const loading = ref(false);
const message = ref('');
const error = ref('');
const createError = ref('');
const editError = ref('');

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
const totalCards = computed(() =>
  deckItems.value.reduce((sum, item) => sum + item.quantity, 0),
);
const visibleSections = computed(() =>
  SECTIONS.filter((section) => section === 'main' || itemsForSection(section).length > 0),
);

function itemsForSection(section: string): WorkspaceDeckItem[] {
  return deckItems.value.filter((item) => item.section === section);
}

function timestampToDate(timestamp: number | null | undefined): Date | null {
  return typeof timestamp === 'number' ? new Date(timestamp * 1000) : null;
}

function dateToTimestamp(date: Date | null): number | null {
  return date ? Math.floor(date.getTime() / 1000) : null;
}

function formatDeckDate(timestamp: number | null | undefined): string {
  if (typeof timestamp !== 'number') {
    return '';
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(
    new Date(timestamp * 1000),
  );
}

function ownerName(playerId: number | null): string {
  if (playerId === null) {
    return 'No owner';
  }
  return players.value.find((player) => player.id === playerId)?.name ?? 'Unknown owner';
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
    return;
  }
  deckItems.value = await listWorkspaceDeckItems(selectedDeckId.value);
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

watch(selectedDeckId, async () => {
  try {
    await refreshDeckItems();
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Deck contents are unavailable');
  }
});

onMounted(() => {
  void refreshAll();
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
      <div class="workspace-heading">
        <div>
          <h1>{{ selectedDeck?.name ?? 'Decks' }}</h1>
          <p v-if="selectedDeck" class="deck-heading-meta">
            {{ selectedDeck.is_wish ? 'Wish deck' : 'Physical deck' }} /
            {{ ownerName(selectedDeck.player_id) }} /
            {{ totalCards }} cards /
            {{ formatDeckDate(selectedDeck.created_at) }}
          </p>
        </div>
      </div>

      <p v-if="message" class="success-text">{{ message }}</p>
      <p v-if="error" class="panel-error" role="alert">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <span>{{ error }}</span>
      </p>

      <section class="deck-search-filters">
        <label class="field">
          <span>Card name</span>
          <InputText v-model="searchQuery" placeholder="Search by name" />
        </label>
        <label class="field">
          <span>Section</span>
          <Select v-model="addSection" :options="[...SECTIONS]" aria-label="Add section" />
        </label>
      </section>

      <section class="deck-search-results">
        <div class="section-header">
          <h2>Search results</h2>
          <span>{{ loading ? 'Loading' : '0' }}</span>
        </div>
        <p class="empty-state">
          Card search and allocation controls are the next deck workflow slice.
        </p>
      </section>
    </main>

    <aside class="inspector-pane deck-contents-pane">
      <div class="workspace-heading">
        <h1>Deck contents</h1>
      </div>
      <section v-if="selectedDeck" class="inspector-content deck-list-content">
        <section v-for="section in visibleSections" :key="section" class="decklist-section">
          <div class="section-header">
            <h2>{{ section }}</h2>
            <span>{{ itemsForSection(section).reduce((sum, item) => sum + item.quantity, 0) }}</span>
          </div>
          <div v-if="itemsForSection(section).length" class="decklist">
            <div v-for="item in itemsForSection(section)" :key="item.id" class="decklist-row">
              <span>{{ item.name }}</span>
              <strong>{{ item.quantity }}</strong>
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
  </section>
</template>

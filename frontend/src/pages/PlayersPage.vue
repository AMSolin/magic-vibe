<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import DatePicker from 'primevue/datepicker';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import ToggleSwitch from 'primevue/toggleswitch';

import {
  createWorkspacePlayer,
  deleteWorkspacePlayer,
  getApiErrorMessage,
  listWorkspaceCollections,
  listWorkspaceDecks,
  listWorkspacePlayers,
  updateWorkspacePlayer,
} from '@/shared/api';
import type { WorkspaceCollection, WorkspaceDeck, WorkspacePlayer } from '@/shared/api';

const router = useRouter();
const sidebarCollapsed = ref(false);
const players = ref<WorkspacePlayer[]>([]);
const collections = ref<WorkspaceCollection[]>([]);
const decks = ref<WorkspaceDeck[]>([]);
const selectedPlayerId = ref<number | null>(null);
const playerName = ref('');
const playerCreatedAt = ref<Date | null>(null);
const playerIsDefault = ref(false);
const createDialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const newPlayerName = ref('');
const createPlayerError = ref('');
const saving = ref(false);
const message = ref('');
const error = ref('');

const selectedPlayer = computed(
  () => players.value.find((player) => player.id === selectedPlayerId.value) ?? null,
);
const affectedCollections = computed(() => {
  const player = selectedPlayer.value;
  if (!player) {
    return [];
  }
  return collections.value.filter((collection) => collection.player_id === player.id);
});
const selectedPlayerCollections = computed(() => affectedCollections.value);
const selectedPlayerDecks = computed(() => {
  const player = selectedPlayer.value;
  if (!player) {
    return [];
  }
  return decks.value.filter((deck) => deck.player_id === player.id);
});
const affectedDecks = computed(() => selectedPlayerDecks.value);

const playerCreatedAtTimestamp = computed(() =>
  playerCreatedAt.value ? Math.floor(playerCreatedAt.value.getTime() / 1000) : null,
);

const playerChanges = computed(() => {
  const player = selectedPlayer.value;
  if (!player) {
    return [];
  }
  return [
    ['Name', player.name, playerName.value],
    ['Created at', formatPlayerDate(player.created_at), formatPlayerDate(playerCreatedAtTimestamp.value)],
    ['Preferred player', player.is_default ? 'Yes' : 'No', playerIsDefault.value ? 'Yes' : 'No'],
  ].filter(([, saved, changed]) => saved !== changed);
});

const playerDirty = computed(() => playerChanges.value.length > 0);
const playerCanSave = computed(
  () =>
    playerDirty.value &&
    Boolean(playerName.value.trim()) &&
    playerCreatedAtTimestamp.value !== null,
);

function timestampToDate(timestamp: number | null | undefined): Date | null {
  return typeof timestamp === 'number' ? new Date(timestamp * 1000) : null;
}

function formatPlayerDate(timestamp: number | null | undefined): string {
  if (typeof timestamp !== 'number') {
    return '';
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp * 1000));
}

function resetPlayerDraft(): void {
  const player = selectedPlayer.value;
  playerName.value = player?.name ?? '';
  playerCreatedAt.value = timestampToDate(player?.created_at);
  playerIsDefault.value = player?.is_default ?? false;
}

function selectPlayer(playerId: number): void {
  if (
    selectedPlayerId.value !== playerId &&
    playerDirty.value &&
    !window.confirm('Discard unsaved player changes?')
  ) {
    return;
  }
  selectedPlayerId.value = playerId;
  message.value = '';
  error.value = '';
}

function openCollection(collectionId: number): void {
  void router.push({ path: '/', query: { collection_id: String(collectionId) } });
}

function openCreatePlayerDialog(): void {
  if (playerDirty.value && !window.confirm('Discard unsaved player changes?')) {
    return;
  }
  newPlayerName.value = '';
  createPlayerError.value = '';
  createDialogVisible.value = true;
}

async function refreshPlayers(preferredSelectedId?: number): Promise<void> {
  players.value = await listWorkspacePlayers();
  selectedPlayerId.value =
    preferredSelectedId ??
    (selectedPlayerId.value &&
    players.value.some((player) => player.id === selectedPlayerId.value)
      ? selectedPlayerId.value
      : players.value.find((player) => player.is_default)?.id ?? players.value[0]?.id ?? null);
}

async function refreshCollections(): Promise<void> {
  collections.value = await listWorkspaceCollections();
}

async function refreshDecks(): Promise<void> {
  decks.value = await listWorkspaceDecks();
}

async function createPlayer(): Promise<void> {
  if (!newPlayerName.value.trim()) {
    return;
  }
  saving.value = true;
  createPlayerError.value = '';
  error.value = '';
  message.value = '';
  try {
    const created = await createWorkspacePlayer({
      name: newPlayerName.value.trim(),
      is_default: players.value.length === 0,
    });
    await refreshPlayers(created.id);
    createDialogVisible.value = false;
    message.value = 'Player created';
  } catch (requestError) {
    createPlayerError.value = getApiErrorMessage(requestError, 'Player could not be created');
  } finally {
    saving.value = false;
  }
}

async function savePlayerChanges(): Promise<void> {
  const player = selectedPlayer.value;
  if (
    !player ||
    !playerDirty.value ||
    !playerName.value.trim() ||
    playerCreatedAtTimestamp.value === null
  ) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    const updated = await updateWorkspacePlayer(player.id, {
      name: playerName.value.trim(),
      is_default: playerIsDefault.value,
      created_at: playerCreatedAtTimestamp.value,
    });
    await refreshPlayers(updated.id);
    resetPlayerDraft();
    message.value = 'Player changes saved';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Player changes could not be saved');
  } finally {
    saving.value = false;
  }
}

async function deletePlayer(): Promise<void> {
  const player = selectedPlayer.value;
  if (!player) {
    return;
  }
  error.value = '';
  message.value = '';
  if (players.value.length <= 1) {
    error.value = 'At least one player must remain';
    return;
  }
  if (affectedCollections.value.length > 0 || affectedDecks.value.length > 0) {
    deleteDialogVisible.value = true;
    return;
  }
  if (!window.confirm(`Delete ${player.name}?`)) {
    return;
  }
  await confirmDeletePlayer(false);
}

async function confirmDeletePlayer(confirmCollectionOwnerClear: boolean): Promise<void> {
  const player = selectedPlayer.value;
  if (!player) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspacePlayer(player.id, confirmCollectionOwnerClear);
    await refreshPlayers();
    await refreshCollections();
    await refreshDecks();
    deleteDialogVisible.value = false;
    message.value = 'Player deleted';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Player could not be deleted');
  } finally {
    saving.value = false;
  }
}

watch(selectedPlayerId, resetPlayerDraft);

onMounted(async () => {
  await refreshPlayers();
  await refreshCollections();
  await refreshDecks();
});
</script>

<template>
  <section class="collection-workspace players-workspace" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <aside class="collection-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <Button
        icon="pi pi-bars"
        severity="secondary"
        text
        :aria-label="sidebarCollapsed ? 'Expand players' : 'Collapse players'"
        @click="sidebarCollapsed = !sidebarCollapsed"
      />
      <template v-if="!sidebarCollapsed">
        <h2>Players</h2>
        <div class="sidebar-list">
          <button
            v-for="player in players"
            :key="player.id"
            type="button"
            :class="{ selected: selectedPlayerId === player.id }"
            @click="selectPlayer(player.id)"
          >
            <span>{{ player.name }}</span>
            <i v-if="player.is_default" class="pi pi-star-fill" title="Preferred player" />
          </button>
        </div>
        <div class="sidebar-actions">
          <Button icon="pi pi-plus" label="Add" size="small" @click="openCreatePlayerDialog" />
          <Button icon="pi pi-trash" label="Delete" size="small" severity="danger" @click="deletePlayer" />
        </div>
      </template>
    </aside>

    <main class="inventory-pane player-empty-pane">
      <div class="workspace-heading">
        <h1>{{ selectedPlayer?.name ?? 'Players' }}</h1>
      </div>
      <section class="player-assets-section">
        <div class="section-header">
          <h2>Collections</h2>
          <span>{{ selectedPlayerCollections.length }}</span>
        </div>
        <div v-if="selectedPlayerCollections.length" class="asset-list">
          <button
            v-for="collection in selectedPlayerCollections"
            :key="collection.id"
            type="button"
            class="asset-row asset-row-button"
            @click="openCollection(collection.id)"
          >
            <span>{{ collection.name }}</span>
            <span class="asset-badges">
              <i v-if="collection.is_default" class="pi pi-star-fill" title="Primary collection" />
              <i v-if="collection.is_wishlist" class="pi pi-heart-fill" title="Wishlist" />
            </span>
          </button>
        </div>
        <p v-else class="empty-state">No collections owned by this player.</p>
      </section>
      <section class="player-assets-section">
        <div class="section-header">
          <h2>Decks</h2>
          <span>{{ selectedPlayerDecks.length }}</span>
        </div>
        <div v-if="selectedPlayerDecks.length" class="asset-list">
          <div v-for="deck in selectedPlayerDecks" :key="deck.id" class="asset-row">
            <span>{{ deck.name }}</span>
            <span class="asset-badges">
              <i v-if="deck.is_wish" class="pi pi-heart-fill" title="Wish deck" />
            </span>
          </div>
        </div>
        <p v-else class="empty-state">No decks owned by this player.</p>
      </section>
    </main>

    <aside class="inspector-pane">
      <div class="workspace-heading">
        <h1>Player info</h1>
      </div>

      <p v-if="error" class="panel-error" role="alert">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <span>{{ error }}</span>
      </p>

      <section v-if="selectedPlayer" class="inspector-content">
        <label class="field"><span>Name</span><InputText v-model="playerName" /></label>
        <label class="field">
          <span>Created at</span>
          <DatePicker
            v-model="playerCreatedAt"
            date-format="yy-mm-dd"
            hour-format="24"
            show-icon
            show-time
          />
        </label>
        <label class="toggle-field">
          <ToggleSwitch
            v-model="playerIsDefault"
            :disabled="selectedPlayer.is_default"
            title="Choose another player to move the preferred marker"
          />
          <span>Preferred player</span>
        </label>
        <details v-if="playerDirty" class="unsaved-changes">
          <summary>Unsaved changes <span>Show details</span></summary>
          <div v-for="[label, saved, changed] in playerChanges" :key="label" class="change-row">
            <strong>{{ label }}</strong>
            <span>{{ saved || 'Empty' }}</span>
            <i class="pi pi-arrow-right" />
            <span>{{ changed || 'Empty' }}</span>
          </div>
        </details>
        <div class="panel-actions edit-actions">
          <span v-if="message" class="success-text">{{ message }}</span>
          <Button
            icon="pi pi-save"
            label="Save changes"
            :disabled="!playerCanSave"
            :loading="saving"
            @click="savePlayerChanges"
          />
          <Button
            label="Discard changes"
            severity="secondary"
            :disabled="!playerDirty"
            @click="resetPlayerDraft"
          />
        </div>
      </section>
    </aside>

    <Dialog v-model:visible="createDialogVisible" modal header="Create player">
      <div class="dialog-fields">
        <label class="field"><span>Name</span><InputText v-model="newPlayerName" autofocus /></label>
        <p v-if="createPlayerError" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ createPlayerError }}</span>
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="createDialogVisible = false" />
          <Button
            icon="pi pi-plus"
            label="Create player"
            :disabled="!newPlayerName.trim()"
            :loading="saving"
            @click="createPlayer"
          />
        </div>
      </template>
    </Dialog>

    <Dialog v-model:visible="deleteDialogVisible" modal header="Delete player">
      <div class="dialog-fields">
        <p class="warning-text">
          This will delete only the player. The owner field will be cleared in these
          collections and decks; their contents will remain.
        </p>
        <ul v-if="affectedCollections.length" class="affected-list">
          <li v-for="collection in affectedCollections" :key="collection.id">
            {{ collection.name }}
          </li>
        </ul>
        <ul v-if="affectedDecks.length" class="affected-list">
          <li v-for="deck in affectedDecks" :key="deck.id">
            {{ deck.name }}
          </li>
        </ul>
        <p v-if="error" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ error }}</span>
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="deleteDialogVisible = false" />
          <Button
            icon="pi pi-trash"
            label="Delete player"
            severity="danger"
            :loading="saving"
            @click="confirmDeletePlayer(true)"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

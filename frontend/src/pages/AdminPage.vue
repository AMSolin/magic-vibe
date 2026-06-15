<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Message from 'primevue/message';
import ProgressSpinner from 'primevue/progressspinner';

import {
  type CatalogImport,
  generateAdminTestCollections,
  type GeneratedTestCollection,
  getApiErrorMessage,
  getCatalogStatus,
  getScryfallSymbolsStatus,
  getUserDataStatus,
  recreateUserData,
  startCatalogRebuild,
  startCatalogUpdate,
  updateScryfallSymbols,
  type CatalogStatus,
  type ScryfallSymbolsStatus,
  type UserDataStatus,
} from '@/shared/api';
import { reloadScryfallSymbols } from '@/shared/scryfallSymbols';

const status = ref<CatalogStatus | null>(null);
const userDataStatus = ref<UserDataStatus | null>(null);
const scryfallSymbolsStatus = ref<ScryfallSymbolsStatus | null>(null);
const loading = ref(false);
const recreatingUserData = ref(false);
const updatingScryfallSymbols = ref(false);
const generatingTestCollections = ref(false);
const generatedTestCollections = ref<GeneratedTestCollection[]>([]);
const userDataDialogVisible = ref(false);
const error = ref<string | null>(null);
const refreshError = ref<string | null>(null);

const latestImport = computed(() => status.value?.latest_import ?? null);
const installedCatalog = computed(() => status.value?.latest_successful_import ?? null);
const catalogOperationRunning = computed(() =>
  ['pending', 'downloading', 'importing'].includes(latestImport.value?.status ?? ''),
);
const rebuildRunning = computed(
  () =>
    catalogOperationRunning.value &&
    latestImport.value?.source === 'Local MTGJSON AllPrintings.sqlite',
);
const updateRunning = computed(() => catalogOperationRunning.value && !rebuildRunning.value);
const userDataButtonLabel = computed(() =>
  userDataStatus.value?.exists ? 'Recreate user database' : 'Initialize user database',
);
const scryfallSymbolsButtonLabel = computed(() =>
  scryfallSymbolsStatus.value?.exists ? 'Update cache' : 'Create cache',
);

let statusTimer: number | undefined;

function formatTimestamp(timestamp: number | null | undefined): string {
  if (timestamp == null) {
    return 'Not available';
  }

  return new Date(timestamp * 1000).toLocaleString();
}

function formatFileSize(size: number | null | undefined): string {
  if (size == null) {
    return 'Not available';
  }

  return new Intl.NumberFormat(undefined, {
    style: 'unit',
    unit: 'megabyte',
    unitDisplay: 'short',
    maximumFractionDigits: 1,
  }).format(size / 1024 / 1024);
}

function formatValue(value: string | number | null | undefined): string {
  return value == null ? 'Not available' : String(value);
}

function statusSeverity(catalogImport: CatalogImport | null): 'success' | 'warn' | 'error' | 'info' {
  if (catalogImport?.status === 'completed') {
    return 'success';
  }
  if (catalogImport?.status === 'failed') {
    return 'error';
  }
  if (catalogImport) {
    return 'warn';
  }
  return 'info';
}

async function loadStatus(showLoading = true): Promise<void> {
  if (showLoading) {
    loading.value = true;
  }
  try {
    [status.value, userDataStatus.value, scryfallSymbolsStatus.value] = await Promise.all([
      getCatalogStatus(),
      getUserDataStatus(),
      getScryfallSymbolsStatus(),
    ]);
    error.value = null;
    refreshError.value = null;
  } catch (caughtError) {
    const message = getApiErrorMessage(caughtError, 'Application status is unavailable');
    if (status.value === null && userDataStatus.value === null && scryfallSymbolsStatus.value === null) {
      error.value = message;
    } else {
      refreshError.value = `${message}. Showing the last known status.`;
    }
  } finally {
    if (showLoading) {
      loading.value = false;
    }
  }
}

async function refreshScryfallSymbols(): Promise<void> {
  updatingScryfallSymbols.value = true;
  error.value = null;
  try {
    scryfallSymbolsStatus.value = await updateScryfallSymbols();
    await reloadScryfallSymbols();
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'Scryfall symbols cache could not be updated');
  } finally {
    updatingScryfallSymbols.value = false;
  }
}

async function initializeUserData(): Promise<void> {
  recreatingUserData.value = true;
  error.value = null;
  try {
    userDataStatus.value = await recreateUserData();
    userDataDialogVisible.value = false;
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'User database could not be initialized');
  } finally {
    recreatingUserData.value = false;
  }
}

async function generateTestCollections(): Promise<void> {
  generatingTestCollections.value = true;
  error.value = null;
  try {
    const result = await generateAdminTestCollections();
    generatedTestCollections.value = result.collections;
    userDataStatus.value = await getUserDataStatus();
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'Test collections could not be generated');
  } finally {
    generatingTestCollections.value = false;
  }
}

async function updateCatalog(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const catalogImport = await startCatalogUpdate();
    status.value = {
      latest_import: catalogImport,
      latest_successful_import: installedCatalog.value,
    };
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'Catalog update could not be started');
  } finally {
    loading.value = false;
  }
}

async function rebuildCatalog(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const catalogImport = await startCatalogRebuild();
    status.value = {
      latest_import: catalogImport,
      latest_successful_import: installedCatalog.value,
    };
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'Catalog rebuild could not be started');
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadStatus();
  statusTimer = window.setInterval(() => loadStatus(false), 3000);
});

onUnmounted(() => {
  if (statusTimer !== undefined) {
    window.clearInterval(statusTimer);
  }
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>Admin</h1>
        <p class="page-description">Catalog maintenance and application status.</p>
      </div>
      <div class="header-actions">
        <Button
          icon="pi pi-refresh"
          label="Refresh all statuses"
          severity="secondary"
          @click="() => loadStatus()"
        />
      </div>
    </div>

    <ProgressSpinner v-if="loading" class="spinner" />
    <Message v-else-if="error" severity="error">{{ error }}</Message>

    <template v-else>
      <Message v-if="refreshError" severity="warn">{{ refreshError }}</Message>

      <section class="tool-panel">
        <div class="section-header">
          <h2>User Database</h2>
          <Message :severity="userDataStatus?.exists ? 'success' : 'warn'" size="small">
            {{ userDataStatus?.exists ? 'Initialized' : 'Not initialized' }}
          </Message>
        </div>

        <div class="metadata-grid">
          <div class="field">
            <span>Database file</span>
            <strong>backend/data/user_data.db</strong>
          </div>
          <div class="field">
            <span>Last modified at</span>
            <strong>{{ formatTimestamp(userDataStatus?.modified_at) }}</strong>
          </div>
          <div class="field">
            <span>File size</span>
            <strong>{{ formatFileSize(userDataStatus?.file_size) }}</strong>
          </div>
        </div>

        <div class="panel-actions">
          <Button
            icon="pi pi-database"
            :label="userDataButtonLabel"
            severity="danger"
            @click="userDataDialogVisible = true"
          />
        </div>
      </section>

      <section class="tool-panel">
        <div class="section-header">
          <h2>Test Data</h2>
        </div>

        <Message severity="info">
          Creates or refreshes the English and Russian 2010+ test collections from the installed
          local catalog. Existing matching rows are reused and kept at least at quantity 4.
        </Message>

        <div v-if="generatedTestCollections.length" class="metadata-grid">
          <div
            v-for="collection in generatedTestCollections"
            :key="collection.id"
            class="field note-field"
          >
            <span>{{ collection.name }}</span>
            <strong>
              #{{ collection.id }} / {{ formatValue(collection.rows) }} rows /
              {{ formatValue(collection.total_quantity) }} cards / {{ collection.language_code }}
            </strong>
          </div>
        </div>

        <div class="panel-actions">
          <Button
            icon="pi pi-clone"
            label="Generate 2010+ test collections"
            :loading="generatingTestCollections"
            :disabled="!userDataStatus?.exists || !installedCatalog"
            @click="generateTestCollections"
          />
        </div>
      </section>

      <section class="tool-panel">
        <div class="section-header">
          <h2>Catalog Database</h2>
          <Message :severity="statusSeverity(installedCatalog)" size="small">
            {{ installedCatalog ? 'Installed' : 'Not installed' }}
          </Message>
        </div>

        <Message severity="info">
          Update downloads the latest MTGJSON source and rebuilds the catalog. Rebuild uses the
          previously downloaded local source without another large download.
        </Message>

        <h3>Installed Catalog</h3>

        <div class="metadata-grid">
          <div class="field">
            <span>Source</span>
            <strong>{{ installedCatalog?.source ?? 'Not available' }}</strong>
          </div>
          <div class="field">
            <span>AllPrintings version date</span>
            <strong>{{ formatTimestamp(installedCatalog?.source_updated_at) }}</strong>
          </div>
          <div class="field">
            <span>Installed at</span>
            <strong>{{ formatTimestamp(installedCatalog?.finished_at) }}</strong>
          </div>
          <div class="field">
            <span>Catalog rows</span>
            <strong>{{ formatValue(installedCatalog?.catalog_row_count) }}</strong>
          </div>
          <div class="field">
            <span>Source file size</span>
            <strong>{{ formatFileSize(installedCatalog?.source_file_size) }}</strong>
          </div>
          <div class="field">
            <span>SHA-256</span>
            <strong class="technical-value">{{ installedCatalog?.source_sha256 ?? 'Not available' }}</strong>
          </div>
        </div>

        <div class="section-header subsection-header">
          <h3>Latest Update Attempt</h3>
          <Message :severity="statusSeverity(latestImport)" size="small">
            {{ latestImport?.status ?? 'No attempts' }}
          </Message>
        </div>

        <div class="metadata-grid">
          <div class="field">
            <span>Started at</span>
            <strong>{{ formatTimestamp(latestImport?.started_at) }}</strong>
          </div>
          <div class="field">
            <span>Finished at</span>
            <strong>{{ formatTimestamp(latestImport?.finished_at) }}</strong>
          </div>
          <div class="field note-field">
            <span>Last error</span>
            <strong>{{ latestImport?.error_message ?? 'None' }}</strong>
          </div>
        </div>

        <div class="panel-actions">
          <Button
            icon="pi pi-database"
            label="Rebuild catalog"
            severity="secondary"
            :disabled="catalogOperationRunning"
            :loading="rebuildRunning"
            @click="rebuildCatalog"
          />
          <Button
            icon="pi pi-download"
            label="Update catalog"
            :disabled="catalogOperationRunning"
            :loading="updateRunning"
            @click="updateCatalog"
          />
        </div>
      </section>

      <section class="tool-panel">
        <div class="section-header">
          <h2>Scryfall Symbols Cache</h2>
          <Message :severity="scryfallSymbolsStatus?.exists ? 'success' : 'warn'" size="small">
            {{ scryfallSymbolsStatus?.exists ? 'Ready' : 'Not created' }}
          </Message>
        </div>

        <Message severity="info">
          Downloads card-symbol SVG files from Scryfall for local reuse throughout the application.
          Existing cached files are retained indefinitely.
        </Message>

        <div class="metadata-grid">
          <div class="field">
            <span>Cache directory</span>
            <strong>backend/data/cache/scryfall/symbols</strong>
          </div>
          <div class="field">
            <span>Cached symbols</span>
            <strong>{{ formatValue(scryfallSymbolsStatus?.symbol_count) }}</strong>
          </div>
          <div class="field">
            <span>Last updated at</span>
            <strong>{{ formatTimestamp(scryfallSymbolsStatus?.updated_at) }}</strong>
          </div>
        </div>

        <div class="panel-actions">
          <Button
            icon="pi pi-download"
            :label="scryfallSymbolsButtonLabel"
            :loading="updatingScryfallSymbols"
            @click="refreshScryfallSymbols"
          />
        </div>
      </section>
    </template>

    <Dialog
      v-model:visible="userDataDialogVisible"
      modal
      :header="userDataButtonLabel"
      class="admin-dialog"
    >
      <p v-if="userDataStatus?.exists">
        Recreating the user database permanently deletes all user collections and decks.
      </p>
      <p v-else>
        Initialize the user database with the default player, collections, decks, and card
        conditions.
      </p>
      <div class="dialog-actions">
        <Button label="Cancel" severity="secondary" text @click="userDataDialogVisible = false" />
        <Button
          :label="userDataButtonLabel"
          severity="danger"
          :loading="recreatingUserData"
          @click="initializeUserData"
        />
      </div>
    </Dialog>
  </section>
</template>

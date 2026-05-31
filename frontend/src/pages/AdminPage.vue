<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import Button from 'primevue/button';
import Message from 'primevue/message';
import ProgressSpinner from 'primevue/progressspinner';

import {
  type CatalogImport,
  getApiErrorMessage,
  getCatalogStatus,
  startCatalogRebuild,
  startCatalogUpdate,
  type CatalogStatus,
} from '@/shared/api';

const status = ref<CatalogStatus | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

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
  error.value = null;
  try {
    status.value = await getCatalogStatus();
  } catch (caughtError) {
    error.value = getApiErrorMessage(caughtError, 'Catalog status is unavailable');
  } finally {
    if (showLoading) {
      loading.value = false;
    }
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
          label="Refresh status"
          severity="secondary"
          @click="() => loadStatus()"
        />
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
    </div>

    <ProgressSpinner v-if="loading" class="spinner" />
    <Message v-else-if="error" severity="error">{{ error }}</Message>

    <template v-else>
      <Message severity="info">
        Update downloads the latest MTGJSON source and rebuilds the catalog. Rebuild uses the
        previously downloaded local source without another large download.
      </Message>

      <section class="tool-panel">
        <div class="section-header">
          <h2>Installed Catalog</h2>
          <Message :severity="statusSeverity(installedCatalog)" size="small">
            {{ installedCatalog?.status ?? 'Not installed' }}
          </Message>
        </div>

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
      </section>

      <section class="tool-panel">
        <div class="section-header">
          <h2>Latest Update Attempt</h2>
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
      </section>
    </template>
  </section>
</template>

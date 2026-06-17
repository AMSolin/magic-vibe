<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';

type ImportType = 'delver-lens-dlens';

const sidebarCollapsed = ref(false);
const selectedImportType = ref<ImportType>('delver-lens-dlens');
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const fileError = ref('');

const importTypeOptions: { label: string; value: ImportType }[] = [
  { label: 'Delver Lens .dlens file', value: 'delver-lens-dlens' },
];

const selectedImportLabel = computed(
  () =>
    importTypeOptions.find((option) => option.value === selectedImportType.value)?.label ??
    'Import source',
);

const selectedFileSize = computed(() => {
  if (!selectedFile.value) {
    return '';
  }
  const size = selectedFile.value.size;
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
});

function chooseFile(): void {
  fileInput.value?.click();
}

function clearSelectedFile(): void {
  selectedFile.value = null;
  fileError.value = '';
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

function handleFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  fileError.value = '';
  selectedFile.value = null;

  if (!file) {
    return;
  }
  if (!file.name.toLowerCase().endsWith('.dlens')) {
    fileError.value = 'Select a .dlens file.';
    input.value = '';
    return;
  }
  selectedFile.value = file;
}
</script>

<template>
  <section class="collection-workspace import-workspace" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <aside class="collection-sidebar import-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <Button
        icon="pi pi-bars"
        severity="secondary"
        text
        :aria-label="sidebarCollapsed ? 'Expand import panel' : 'Collapse import panel'"
        @click="sidebarCollapsed = !sidebarCollapsed"
      />
      <template v-if="!sidebarCollapsed">
        <h2>Import</h2>
        <label class="field">
          <span>Source</span>
          <Select
            v-model="selectedImportType"
            :options="importTypeOptions"
            option-label="label"
            option-value="value"
          />
        </label>

        <section v-if="selectedImportType === 'delver-lens-dlens'" class="import-upload-widget">
          <input
            ref="fileInput"
            class="visually-hidden-file-input"
            type="file"
            accept=".dlens"
            @change="handleFileChange"
          />
          <Button icon="pi pi-upload" label="Choose .dlens" size="small" @click="chooseFile" />
          <div v-if="selectedFile" class="import-selected-file">
            <i class="pi pi-database" aria-hidden="true" />
            <div>
              <strong>{{ selectedFile.name }}</strong>
              <span>{{ selectedFileSize }}</span>
            </div>
            <Button
              icon="pi pi-times"
              severity="secondary"
              text
              rounded
              aria-label="Clear selected file"
              title="Clear selected file"
              @click="clearSelectedFile"
            />
          </div>
          <p v-if="fileError" class="panel-error" role="alert">
            <i class="pi pi-exclamation-triangle" aria-hidden="true" />
            <span>{{ fileError }}</span>
          </p>
        </section>
      </template>
    </aside>

    <main class="inventory-pane import-preview-pane">
      <div class="workspace-heading">
        <h1>{{ selectedImportLabel }}</h1>
        <p>{{ selectedFile ? selectedFile.name : 'No file selected' }}</p>
      </div>
      <section class="empty-state import-empty-state">
        <i class="pi pi-file-import" aria-hidden="true" />
        <span>Import preview will appear here.</span>
      </section>
    </main>

    <aside class="inspector-pane import-inspector-pane">
      <div class="workspace-heading">
        <h1>Details</h1>
        <p>{{ selectedFile ? selectedFileSize : 'Awaiting file' }}</p>
      </div>
      <section class="inspector-content">
        <div class="card-attributes">
          <span>Source</span>
          <strong>{{ selectedImportLabel }}</strong>
        </div>
        <div class="card-attributes">
          <span>File</span>
          <strong>{{ selectedFile?.name ?? 'None' }}</strong>
        </div>
      </section>
    </aside>
  </section>
</template>

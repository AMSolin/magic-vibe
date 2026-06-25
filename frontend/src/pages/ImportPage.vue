<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import Button from 'primevue/button';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import DatePicker from 'primevue/datepicker';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Message from 'primevue/message';
import Select from 'primevue/select';
import Tab from 'primevue/tab';
import TabList from 'primevue/tablist';
import Tabs from 'primevue/tabs';
import Textarea from 'primevue/textarea';

import ScryfallSymbolsText from '@/components/ScryfallSymbolsText.vue';
import {
  applyDelverLensImport,
  clearDelverLensImportSession,
  deleteDelverLensImportEntity,
  getDelverLensImportSession,
  getApiErrorMessage,
  listWorkspaceCollections,
  listWorkspaceDecks,
  listWorkspacePlayers,
  mergeDelverLensImportEntity,
  previewDelverLensImport,
  updateDelverLensImportEntity,
  type DelverLensImportAttributeChange,
  type DelverLensImportCard,
  type DelverLensImportEntity,
  type DelverLensImportEntityEdit,
  type DelverLensImportPreview,
  type DelverLensImportResult,
  type ImportMergeSection,
  type ImportTargetType,
  type WorkspaceCollection,
  type WorkspaceDeck,
  type WorkspacePlayer,
} from '@/shared/api';
import { loadScryfallSymbols } from '@/shared/scryfallSymbols';

type ImportType = 'delver-lens-dlens';
type TargetOption = { label: string; value: string };
type TargetCollectionSelectValue = string | TargetOption | null;
type ImportInfoChange = [string, string, string];
type ImportEntityDraft = {
  target_type: ImportTargetType;
  name: string;
  player_id: number;
  created_at: Date | null;
  target_collection_value: TargetCollectionSelectValue;
  note: string | null;
};
type ImportCardGroup = {
  key: string;
  name: string;
  quantity: number;
  cards: DelverLensImportCard[];
};
type ImportCardSection = {
  key: string;
  label: string;
  groups: ImportCardGroup[];
};
type MergeTargetOption = {
  label: string;
  value: number;
};
type PreviewCandidate = {
  printing_id: number;
  language_code: string;
  name: string;
};
type AttributeChangeCardGroup = {
  key: string;
  name: string;
  quantity: number;
  changes: DelverLensImportAttributeChange[];
};
type AttributeChangeContainerGroup = {
  key: string;
  name: string;
  cards: AttributeChangeCardGroup[];
  changeCount: number;
};

const TARGET_TYPE_OPTIONS: { label: string; value: ImportTargetType }[] = [
  { label: 'Collection', value: 'collection' },
  { label: 'Wishlist', value: 'wishlist' },
  { label: 'Deck', value: 'deck' },
  { label: 'Wish deck', value: 'wishdeck' },
];

const SECTION_ORDER = ['commander', 'main', 'side', 'maybe'];
const SECTION_OPTIONS: { label: string; value: ImportMergeSection }[] = [
  { label: 'Main', value: 'main' },
  { label: 'Sideboard', value: 'side' },
  { label: 'Maybeboard', value: 'maybe' },
  { label: 'Commander', value: 'commander' },
];
const KEEP_SECTION_OPTION: { label: string; value: ImportMergeSection } = {
  label: 'Keep sections',
  value: 'keep',
};
const NON_BLOCKING_CARD_ERROR_PREFIXES = ['Delver card id '];
const NON_BLOCKING_CARD_ERROR_FRAGMENTS = [' is not mapped', ' does not resolve to catalog'];
const HOVER_PREVIEW_DELAY_MS = 450;
const CARD_NORMAL_IMAGE_WIDTH = 488;
const CARD_NORMAL_IMAGE_HEIGHT = 680;
const HOVER_PREVIEW_WIDTH = Math.round(CARD_NORMAL_IMAGE_WIDTH * 0.75);
const HOVER_PREVIEW_HEIGHT = Math.round(
  HOVER_PREVIEW_WIDTH * (CARD_NORMAL_IMAGE_HEIGHT / CARD_NORMAL_IMAGE_WIDTH),
);
const IMPORT_SESSION_STORAGE_KEY = 'magic-vibe:delver-lens-import-session-id';

const sidebarCollapsed = ref(false);
const selectedImportType = ref<ImportType>('delver-lens-dlens');
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const fileError = ref('');
const previewError = ref('');
const importMessage = ref('');
const previewLoading = ref(false);
const applyingImport = ref(false);
const actionLoading = ref(false);
const preview = ref<DelverLensImportPreview | null>(null);
const importSessionId = ref<string | null>(null);
const importEntities = ref<DelverLensImportEntity[]>([]);
const selectedEntity = ref<DelverLensImportEntity | null>(null);
const selectedEntityDraft = ref<ImportEntityDraft | null>(null);
const activeInspectorTab = ref('info');
const players = ref<WorkspacePlayer[]>([]);
const collections = ref<WorkspaceCollection[]>([]);
const decks = ref<WorkspaceDeck[]>([]);
const importResult = ref<DelverLensImportResult | null>(null);
const importCompleted = ref(false);
const changeDialogVisible = ref(false);
const mergeTargetEntityId = ref<number | null>(null);
const mergeSection = ref<ImportMergeSection>('main');
const expandedImportCardGroups = ref<Set<string>>(new Set());
const hoverPreview = ref<{
  imageUrl: string;
  fallbackImageUrl: string | null;
  label: string;
  x: number;
  y: number;
} | null>(null);
const hoverPreviewLoading = ref(false);
const hoverPreviewError = ref(false);
let hoverPreviewTimer: number | null = null;
let hoverPreviewRequestId = 0;

const importTypeOptions: { label: string; value: ImportType }[] = [
  { label: 'Delver Lens .dlens file', value: 'delver-lens-dlens' },
];

const selectedImportLabel = computed(
  () =>
    importTypeOptions.find((option) => option.value === selectedImportType.value)?.label ??
    'Import method',
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
const activeImportFilename = computed(() => selectedFile.value?.name ?? preview.value?.source_filename ?? '');
const activeImportFileMeta = computed(() => selectedFileSize.value || (importSessionId.value ? 'Restored session' : ''));

const regularCollections = computed(() => collections.value.filter((collection) => !collection.is_wishlist));
const wishlistCollections = computed(() => collections.value.filter((collection) => collection.is_wishlist));
const importAttributeChangeGroups = computed<AttributeChangeContainerGroup[]>(() => {
  const groups = new Map<string, AttributeChangeContainerGroup>();
  for (const change of importResult.value?.attribute_changes ?? []) {
    const containerKey = `${change.source_list_id}:${change.container_name}`;
    let container = groups.get(containerKey);
    if (!container) {
      container = {
        key: containerKey,
        name: change.container_name,
        cards: [],
        changeCount: 0,
      };
      groups.set(containerKey, container);
    }
    const cardKey = `${change.source_card_id}:${change.card_name}`;
    let card = container.cards.find((candidate) => candidate.key === cardKey);
    if (!card) {
      card = {
        key: cardKey,
        name: change.card_name,
        quantity: change.quantity,
        changes: [],
      };
      container.cards.push(card);
    }
    card.changes.push(change);
    container.changeCount += 1;
  }
  return [...groups.values()];
});

const totalRows = computed(() => importEntities.value.length);
const totalCards = computed(() =>
  importEntities.value.reduce((sum, entity) => sum + entity.total_quantity, 0),
);
const totalValidationErrors = computed(() =>
  importCompleted.value
    ? 0
    : importEntities.value.reduce((sum, entity) => sum + entityDisplayValidationErrors(entity).length, 0),
);
const totalWarnings = computed(() =>
  importCompleted.value
    ? 0
    : importEntities.value.reduce((sum, entity) => sum + entityIssueWarningCount(entity), 0),
);

const canApply = computed(
  () =>
    importSessionId.value !== null &&
    importEntities.value.length > 0 &&
    !importCompleted.value &&
    !previewLoading.value &&
    !applyingImport.value &&
    !actionLoading.value &&
    totalValidationErrors.value === 0 &&
    !importInfoDirty.value,
);

const selectedImportCardSections = computed<ImportCardSection[]>(() => {
  const entity = selectedEntity.value;
  if (!entity) {
    return [];
  }
  if (entity.target_type === 'collection' || entity.target_type === 'wishlist') {
    return [
      {
        key: 'cards',
        label: 'Cards',
        groups: groupedImportCards(entity.cards, 'cards'),
      },
    ];
  }
  return SECTION_ORDER.map((section) => ({
    key: section,
    label: sectionLabel(section),
    groups: groupedImportCards(
      entity.cards.filter((card) => card.section === section),
      section,
    ),
  })).filter((section) => section.groups.length > 0 || section.key === 'main');
});
const selectedUnrecognizedCards = computed(() => {
  const entity = selectedEntity.value;
  return entity ? entity.cards.filter((card) => unrecognizedCardWarning(card) !== null) : [];
});
const importInfoChanges = computed<ImportInfoChange[]>(() => {
  const entity = selectedEntity.value;
  const draft = selectedEntityDraft.value;
  if (!entity || !draft) {
    return [];
  }
  return [
    importInfoChange(
      'Target type',
      targetTypeLabel(entity.target_type),
      targetTypeLabel(draft.target_type),
      entity.target_type,
      draft.target_type,
    ),
    importInfoChange('Name', entity.name, draft.name, entity.name.trim(), draft.name.trim()),
    importInfoChange('Owner', playerName(entity.player_id), playerName(draft.player_id), entity.player_id, draft.player_id),
    importInfoChange(
      'Created at',
      formatDateTime(entity.created_at),
      formatDraftDateTime(draft.created_at),
      entity.created_at,
      draft.created_at ? dateToTimestamp(draft.created_at) : entity.created_at,
    ),
    importInfoChange(
      'Target collection',
      entityTargetSummary(entity),
      draftTargetCollectionSummary(draft),
      targetCollectionValue(entity),
      normalizeTargetCollectionValue(draft.target_collection_value),
    ),
    importInfoChange('Note', entity.note ?? '', draft.note ?? '', entity.note ?? '', draft.note ?? ''),
  ].filter((change): change is ImportInfoChange => change !== null);
});
const importInfoDirty = computed(() => importInfoChanges.value.length > 0);
const importInfoDraftErrors = computed(() => {
  const entity = selectedEntity.value;
  const draft = selectedEntityDraft.value;
  if (!entity || !draft) {
    return [];
  }
  return entityValidationErrors(importEntityDraftToEntity(entity, draft));
});
const activeImportInfoErrors = computed(() =>
  selectedEntity.value && !importCompleted.value ? importInfoDraftErrors.value : [],
);
const selectedIssueCount = computed(() =>
  selectedEntity.value && !importCompleted.value
    ? activeImportInfoErrors.value.length + entityIssueWarningCount(selectedEntity.value)
    : 0,
);
const hasSelectedIssues = computed(() => selectedIssueCount.value > 0);
const importInfoCanSave = computed(() => importInfoDirty.value && !importCompleted.value && !actionLoading.value);
const selectedEntityMergeTargets = computed(() =>
  selectedEntity.value
    ? importEntities.value.filter((entity) => entity.id !== selectedEntity.value?.id)
    : [],
);
const selectedEntityMergeTargetOptions = computed<MergeTargetOption[]>(() =>
  selectedEntityMergeTargets.value.map((entity) => ({
    label: mergeTargetLabel(entity),
    value: entity.id,
  })),
);
const selectedMergeTarget = computed(
  () => importEntities.value.find((entity) => entity.id === mergeTargetEntityId.value) ?? null,
);
const mergeSectionOptions = computed(() => {
  const source = selectedEntity.value;
  const target = selectedMergeTarget.value;
  if (!source || !target || (target.target_type !== 'deck' && target.target_type !== 'wishdeck')) {
    return [];
  }
  if (
    (source.target_type === 'deck' || source.target_type === 'wishdeck') &&
    (target.target_type === 'deck' || target.target_type === 'wishdeck')
  ) {
    return [KEEP_SECTION_OPTION, ...SECTION_OPTIONS];
  }
  return SECTION_OPTIONS;
});
const canMergeSelectedEntity = computed(
  () =>
    !importCompleted.value &&
    !actionLoading.value &&
    selectedEntity.value !== null &&
    mergeTargetEntityId.value !== null,
);
const hoverPreviewStyle = computed(() => {
  if (!hoverPreview.value) {
    return {};
  }
  const previewWidth = HOVER_PREVIEW_WIDTH;
  const previewHeight = HOVER_PREVIEW_HEIGHT;
  const gap = 14;
  const viewportPadding = 12;
  const maxLeft = Math.max(viewportPadding, window.innerWidth - previewWidth - viewportPadding);
  const maxTop = Math.max(viewportPadding, window.innerHeight - previewHeight - viewportPadding);
  const inspectorPane = document.querySelector('.import-inspector-pane');
  const previewPane = document.querySelector('.import-preview-pane');
  const inspectorRect = inspectorPane?.getBoundingClientRect();
  const previewRect = previewPane?.getBoundingClientRect();
  const canAnchorLeftOfInspector = Boolean(
    inspectorRect &&
      previewRect &&
      inspectorRect.width > 0 &&
      previewRect.width > 0 &&
      previewRect.right <= inspectorRect.left &&
      inspectorRect.left - gap - previewWidth >= viewportPadding,
  );
  const cursorLeft = hoverPreview.value.x + gap;
  const cursorTop = hoverPreview.value.y + gap;
  const fallbackLeft =
    cursorLeft + previewWidth <= window.innerWidth - viewportPadding
      ? cursorLeft
      : hoverPreview.value.x - previewWidth - gap;
  const fallbackTop =
    cursorTop + previewHeight <= window.innerHeight - viewportPadding
      ? cursorTop
      : hoverPreview.value.y - previewHeight - gap;
  const left = canAnchorLeftOfInspector
    ? inspectorRect!.left - gap - previewWidth
    : fallbackLeft;
  const top = canAnchorLeftOfInspector ? hoverPreview.value.y + gap : fallbackTop;
  return {
    left: `${Math.min(Math.max(viewportPadding, left), maxLeft)}px`,
    top: `${Math.min(Math.max(viewportPadding, top), maxTop)}px`,
  };
});

onMounted(async () => {
  await Promise.all([refreshWorkspaceData(), loadScryfallSymbols(), restoreImportSession()]);
});

onBeforeUnmount(() => {
  clearHoverPreviewTimer();
});

watch(selectedEntity, (entity) => {
  selectedEntityDraft.value = entity ? importEntityDraftFromEntity(entity) : null;
  mergeTargetEntityId.value = selectedEntityMergeTargets.value[0]?.id ?? null;
  expandedImportCardGroups.value = new Set();
  activeInspectorTab.value = 'info';
  stopHoverPreview();
});

watch([selectedEntity, selectedMergeTarget], () => {
  mergeSection.value = mergeSectionOptions.value[0]?.value ?? 'main';
});

watch(hasSelectedIssues, (hasIssues) => {
  if (!hasIssues && activeInspectorTab.value === 'issues') {
    activeInspectorTab.value = 'info';
  }
});

watch(importCompleted, (completed) => {
  if (completed && (activeInspectorTab.value === 'actions' || activeInspectorTab.value === 'issues')) {
    activeInspectorTab.value = 'info';
  }
});

function importInfoChange(
  label: string,
  saved: string,
  changed: string,
  savedCompare: string | number | null,
  changedCompare: string | number | null,
): ImportInfoChange | null {
  return savedCompare === changedCompare ? null : [label, saved, changed];
}

function chooseFile(): void {
  fileInput.value?.click();
}

async function clearSelectedFile(): Promise<void> {
  const sessionId = importSessionId.value;
  localStorage.removeItem(IMPORT_SESSION_STORAGE_KEY);
  if (sessionId) {
    try {
      await clearDelverLensImportSession(sessionId);
    } catch {
      // The local UI state should still be cleared if the session was already gone.
    }
  }
  selectedFile.value = null;
  fileError.value = '';
  previewError.value = '';
  importMessage.value = '';
  preview.value = null;
  importSessionId.value = null;
  importEntities.value = [];
  selectedEntity.value = null;
  selectedEntityDraft.value = null;
  importResult.value = null;
  importCompleted.value = false;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

async function refreshWorkspaceData(): Promise<void> {
  [players.value, collections.value, decks.value] = await Promise.all([
    listWorkspacePlayers(),
    listWorkspaceCollections(),
    listWorkspaceDecks(),
  ]);
}

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  await clearSelectedFile();

  if (!file) {
    return;
  }
  if (!file.name.toLowerCase().endsWith('.dlens')) {
    fileError.value = 'Select a .dlens file.';
    input.value = '';
    return;
  }
  selectedFile.value = file;
  await loadPreview(file);
}

async function loadPreview(file: File): Promise<void> {
  previewLoading.value = true;
  previewError.value = '';
  importMessage.value = '';
  importCompleted.value = false;
  importResult.value = null;
  try {
    await refreshWorkspaceData();
    const result = await previewDelverLensImport(file);
    applyPreviewState(result);
    activeInspectorTab.value = 'info';
  } catch (error) {
    previewError.value = getApiErrorMessage(error, 'Delver Lens file could not be parsed');
    preview.value = null;
    importSessionId.value = null;
    localStorage.removeItem(IMPORT_SESSION_STORAGE_KEY);
    importEntities.value = [];
    selectedEntity.value = null;
  } finally {
    previewLoading.value = false;
  }
}

function targetTypeLabel(type: ImportTargetType): string {
  return TARGET_TYPE_OPTIONS.find((option) => option.value === type)?.label ?? type;
}

function playerName(playerId: number | null): string {
  if (playerId === null) {
    return 'No owner';
  }
  return players.value.find((player) => player.id === playerId)?.name ?? `Player ${playerId}`;
}

function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function formatDraftDateTime(date: Date | null): string {
  return date ? date.toLocaleString() : '';
}

function timestampToDate(timestamp: number): Date {
  return new Date(timestamp * 1000);
}

function dateToTimestamp(date: Date): number {
  return Math.floor(date.getTime() / 1000);
}

function sectionLabel(section: string): string {
  if (section === 'commander') {
    return 'Commander';
  }
  if (section === 'side') {
    return 'Sideboard';
  }
  if (section === 'maybe') {
    return 'Maybeboard';
  }
  return 'Main';
}

function collectionLabel(collection: WorkspaceCollection): string {
  return `${collection.name} (${playerName(collection.player_id)})`;
}

function normalizedImportName(name: string): string {
  return name.trim().toLocaleLowerCase();
}

function importedCollectionOptions(entity: DelverLensImportEntity): TargetOption[] {
  return importEntities.value
    .filter(
      (candidate) =>
        candidate.id !== entity.id &&
        candidate.target_type === 'collection' &&
        candidate.target_collection_mode === 'new',
    )
    .map((candidate) => ({
      label: `${candidate.name} (new import)`,
      value: `import:${candidate.id}`,
    }));
}

function targetCollectionOptions(entity: DelverLensImportEntity): TargetOption[] {
  if (entity.target_type === 'wishdeck') {
    return [];
  }
  if (entity.target_type === 'collection') {
    return [
      { label: 'New collection', value: 'new' },
      ...regularCollections.value.map((collection) => ({
        label: collectionLabel(collection),
        value: `existing:${collection.id}`,
      })),
    ];
  }
  if (entity.target_type === 'wishlist') {
    return [
      { label: 'New wishlist', value: 'new' },
      ...wishlistCollections.value.map((collection) => ({
        label: collectionLabel(collection),
        value: `existing:${collection.id}`,
      })),
    ];
  }
  return [
    ...regularCollections.value.map((collection) => ({
      label: collectionLabel(collection),
      value: `existing:${collection.id}`,
    })),
    ...importedCollectionOptions(entity),
  ];
}

function targetCollectionValue(entity: DelverLensImportEntity): string | null {
  if (entity.target_collection_mode === 'new') {
    return 'new';
  }
  if (entity.target_collection_mode === 'existing' && entity.target_collection_id !== null) {
    return `existing:${entity.target_collection_id}`;
  }
  if (entity.target_collection_mode === 'import' && entity.target_import_list_id !== null) {
    return `import:${entity.target_import_list_id}`;
  }
  return null;
}

function importEntityDraftFromEntity(entity: DelverLensImportEntity): ImportEntityDraft {
  return {
    target_type: entity.target_type,
    name: entity.name,
    player_id: entity.player_id,
    created_at: timestampToDate(entity.created_at),
    target_collection_value: targetCollectionValue(entity),
    note: entity.note,
  };
}

function draftTargetCollectionOptions(draft: ImportEntityDraft): TargetOption[] {
  const entity = selectedEntity.value;
  if (!entity) {
    return [];
  }
  return targetCollectionOptionsForTargetType(entity, draft.target_type);
}

function draftTargetCollectionSummary(draft: ImportEntityDraft): string {
  const entity = selectedEntity.value;
  const targetValue = normalizeTargetCollectionValue(draft.target_collection_value);
  if (!entity || draft.target_type === 'wishdeck') {
    return 'Wish deck';
  }
  if (targetValue === 'new') {
    return draft.target_type === 'wishlist' ? 'New wishlist' : 'New collection';
  }
  return (
    draftTargetCollectionOptions(draft).find((option) => option.value === targetValue)?.label ??
    'Required'
  );
}

function targetCollectionOptionsForTargetType(
  entity: DelverLensImportEntity,
  targetType: ImportTargetType,
): TargetOption[] {
  if (targetType === 'wishdeck') {
    return [];
  }
  if (targetType === 'collection') {
    return [
      { label: 'New collection', value: 'new' },
      ...regularCollections.value.map((collection) => ({
        label: collectionLabel(collection),
        value: `existing:${collection.id}`,
      })),
    ];
  }
  if (targetType === 'wishlist') {
    return [
      { label: 'New wishlist', value: 'new' },
      ...wishlistCollections.value.map((collection) => ({
        label: collectionLabel(collection),
        value: `existing:${collection.id}`,
      })),
    ];
  }
  return [
    ...regularCollections.value.map((collection) => ({
      label: collectionLabel(collection),
      value: `existing:${collection.id}`,
    })),
    ...importedCollectionOptions(entity),
  ];
}

function normalizeTargetCollectionValue(value: TargetCollectionSelectValue): string | null {
  if (typeof value === 'string' || value === null) {
    return value;
  }
  return value.value;
}

function updateDraftTargetCollection(draft: ImportEntityDraft, value: TargetCollectionSelectValue): void {
  draft.target_collection_value = normalizeTargetCollectionValue(value);
}

function applyTargetCollectionValue(entity: DelverLensImportEntity, value: TargetCollectionSelectValue): void {
  const normalizedValue = normalizeTargetCollectionValue(value);
  entity.target_collection_id = null;
  entity.target_import_list_id = null;
  if (normalizedValue === 'new') {
    entity.target_collection_mode = 'new';
    return;
  }
  if (normalizedValue?.startsWith('existing:')) {
    entity.target_collection_mode = 'existing';
    entity.target_collection_id = Number(normalizedValue.split(':')[1]);
    return;
  }
  if (normalizedValue?.startsWith('import:')) {
    entity.target_collection_mode = 'import';
    entity.target_import_list_id = Number(normalizedValue.split(':')[1]);
    return;
  }
  entity.target_collection_mode = null;
}

function importEntityDraftToEntity(
  entity: DelverLensImportEntity,
  draft: ImportEntityDraft,
): DelverLensImportEntity {
  const draftEntity = {
    ...entity,
    target_type: draft.target_type,
    target_type_label: targetTypeLabel(draft.target_type),
    name: draft.name,
    player_id: draft.player_id,
    created_at: draft.created_at ? dateToTimestamp(draft.created_at) : entity.created_at,
    note: draft.note,
  };
  applyTargetCollectionValue(draftEntity, draft.target_collection_value);
  return draftEntity;
}

function updateDraftTargetType(draft: ImportEntityDraft, type: ImportTargetType): void {
  draft.target_type = type;
  if (type === 'collection' || type === 'wishlist') {
    draft.target_collection_value = 'new';
  } else {
    draft.target_collection_value = null;
  }
}

async function saveImportInfoChanges(): Promise<void> {
  const entity = selectedEntity.value;
  const draft = selectedEntityDraft.value;
  if (!entity || !draft || !importSessionId.value || !importInfoDirty.value || importCompleted.value) {
    return;
  }
  previewError.value = '';
  const draftEntity = importEntityDraftToEntity(entity, draft);
  try {
    const result = await updateDelverLensImportEntity(
      importSessionId.value,
      entity.id,
      entityEditPayload(draftEntity),
    );
    applyPreviewState(result);
  } catch (error) {
    previewError.value = getApiErrorMessage(error, 'Import settings could not be saved');
  }
}

async function restoreImportSession(): Promise<void> {
  const sessionId = localStorage.getItem(IMPORT_SESSION_STORAGE_KEY);
  if (!sessionId || importSessionId.value) {
    return;
  }
  previewLoading.value = true;
  previewError.value = '';
  importMessage.value = '';
  try {
    const result = await getDelverLensImportSession(sessionId);
    applyPreviewState(result);
  } catch (error) {
    localStorage.removeItem(IMPORT_SESSION_STORAGE_KEY);
    preview.value = null;
    importSessionId.value = null;
    importEntities.value = [];
    selectedEntity.value = null;
    previewError.value = getApiErrorMessage(error, 'Saved import session could not be restored');
  } finally {
    previewLoading.value = false;
  }
}

function discardImportInfoChanges(): void {
  if (!selectedEntity.value) {
    selectedEntityDraft.value = null;
    return;
  }
  selectedEntityDraft.value = importEntityDraftFromEntity(selectedEntity.value);
}

function existingCollectionNameConflict(entity: DelverLensImportEntity): boolean {
  if (entity.target_type !== 'collection' && entity.target_type !== 'wishlist') {
    return false;
  }
  if (entity.target_collection_mode !== 'new') {
    return false;
  }
  return collections.value.some(
    (collection) =>
      collection.player_id === entity.player_id &&
      normalizedImportName(collection.name) === normalizedImportName(entity.name),
  );
}

function existingDeckNameConflict(entity: DelverLensImportEntity): boolean {
  if (entity.target_type !== 'deck' && entity.target_type !== 'wishdeck') {
    return false;
  }
  return decks.value.some(
    (deck) =>
      deck.player_id === entity.player_id &&
      normalizedImportName(deck.name) === normalizedImportName(entity.name),
  );
}

function duplicateImportName(entity: DelverLensImportEntity): boolean {
  const sameName = (candidate: DelverLensImportEntity) =>
    candidate.id !== entity.id &&
    candidate.player_id === entity.player_id &&
    normalizedImportName(candidate.name) === normalizedImportName(entity.name);
  if (entity.target_type === 'collection' || entity.target_type === 'wishlist') {
    return entity.target_collection_mode === 'new' && importEntities.value.some((candidate) => {
      return (
        (candidate.target_type === 'collection' || candidate.target_type === 'wishlist') &&
        candidate.target_collection_mode === 'new' &&
        sameName(candidate)
      );
    });
  }
  return importEntities.value.some((candidate) => {
    return (
      (candidate.target_type === 'deck' || candidate.target_type === 'wishdeck') &&
      sameName(candidate)
    );
  });
}

function entityValidationErrors(entity: DelverLensImportEntity): string[] {
  const errors = entity.cards.flatMap((card) => blockingCardErrors(card, entity.target_type));
  if (!entity.name.trim()) {
    errors.push('Name is required.');
  }
  if (!entity.player_id) {
    errors.push('Owner is required.');
  }
  if (existingCollectionNameConflict(entity)) {
    errors.push('Collection with this name already exists for this owner.');
  }
  if (existingDeckNameConflict(entity)) {
    errors.push('Deck with this name already exists for this owner.');
  }
  if (duplicateImportName(entity)) {
    errors.push('Another imported entity uses this name for the same owner.');
  }
  if (entity.target_type === 'deck' && targetCollectionValue(entity) === null) {
    errors.push('Physical deck must target a regular collection.');
  }
  if (entity.target_type === 'collection' && entity.target_collection_mode === 'existing') {
    const target = regularCollections.value.find((collection) => collection.id === entity.target_collection_id);
    if (!target) {
      errors.push('Collection can merge only into an existing regular collection.');
    }
  }
  if (entity.target_type === 'wishlist' && entity.target_collection_mode === 'existing') {
    const target = wishlistCollections.value.find((collection) => collection.id === entity.target_collection_id);
    if (!target) {
      errors.push('Wishlist can merge only into an existing wishlist collection.');
    }
  }
  return Array.from(new Set(errors));
}

function blockingCardErrors(card: DelverLensImportCard, targetType: ImportTargetType): string[] {
  const errors = card.errors.filter((error) => !isNonBlockingCardError(error));
  if (targetType === 'wishdeck') {
    return errors.filter(
      (error) =>
        !error.startsWith('Unknown Delver condition:') &&
        !error.startsWith('No legal finish is available'),
    );
  }
  return errors;
}

function isNonBlockingCardError(error: string): boolean {
  return (
    NON_BLOCKING_CARD_ERROR_PREFIXES.some((prefix) => error.startsWith(prefix)) &&
    NON_BLOCKING_CARD_ERROR_FRAGMENTS.some((fragment) => error.includes(fragment))
  );
}

function entitySeverity(entity: DelverLensImportEntity): 'success' | 'warn' | 'error' {
  if (importCompleted.value) {
    return 'success';
  }
  if (entityDisplayValidationErrors(entity).length > 0) {
    return 'error';
  }
  if (entityIssueWarningCount(entity) > 0) {
    return 'warn';
  }
  return 'success';
}

function entityStatusLabel(entity: DelverLensImportEntity): string {
  if (importCompleted.value) {
    return 'Imported';
  }
  if (entityDisplayValidationErrors(entity).length > 0) {
    return 'Error';
  }
  if (entityIssueWarningCount(entity) > 0) {
    return 'Warning';
  }
  return 'Ready';
}

function entityDisplayValidationErrors(entity: DelverLensImportEntity): string[] {
  if (importCompleted.value) {
    return [];
  }
  return entityValidationErrors(entity);
}

function entityPlainWarnings(entity: DelverLensImportEntity): string[] {
  const attributeChangeReasons = new Set(
    entity.attribute_changes.map((change) => change.reason).filter((reason): reason is string => Boolean(reason)),
  );
  return entity.warnings.filter((warning) => !attributeChangeReasons.has(warning));
}

function entityWarningCount(entity: DelverLensImportEntity): number {
  return entity.attribute_changes.length + entityPlainWarnings(entity).length;
}

function entityIssueWarningCount(entity: DelverLensImportEntity): number {
  return entityWarningCount(entity) + entity.cards.filter((card) => unrecognizedCardWarning(card) !== null).length;
}

function entityTargetSummary(entity: DelverLensImportEntity): string {
  const value = targetCollectionValue(entity);
  if (entity.target_type === 'wishdeck') {
    return 'Wish deck';
  }
  if (value === 'new') {
    return entity.target_type === 'wishlist' ? 'New wishlist' : 'New collection';
  }
  if (value?.startsWith('existing:')) {
    const id = Number(value.split(':')[1]);
    const collection = collections.value.find((item) => item.id === id);
    return collection ? collection.name : 'Existing collection';
  }
  if (value?.startsWith('import:')) {
    const id = Number(value.split(':')[1]);
    return importEntities.value.find((item) => item.id === id)?.name ?? 'Imported collection';
  }
  return 'Required';
}

function groupedImportCards(cards: DelverLensImportCard[], sectionKey: string): ImportCardGroup[] {
  const rows = new Map<string, ImportCardGroup>();
  for (const card of cards) {
    const groupKey = card.oracle_id ?? `source:${card.source_card_id}`;
    const row = rows.get(groupKey);
    if (row) {
      row.quantity += card.quantity;
      row.cards.push(card);
    } else {
      rows.set(groupKey, {
        key: `${sectionKey}:${groupKey}`,
        name: card.name,
        quantity: card.quantity,
        cards: [card],
      });
    }
  }
  return [...rows.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function importCardPreviewCandidate(card: DelverLensImportCard): PreviewCandidate | null {
  if (card.printing_id === null || card.language_code === null) {
    return null;
  }
  return {
    printing_id: card.printing_id,
    language_code: card.language_code,
    name: card.name,
  };
}

function importCardGroupPreviewCandidate(group: ImportCardGroup): PreviewCandidate | null {
  for (const card of group.cards) {
    const candidate = importCardPreviewCandidate(card);
    if (candidate) {
      return candidate;
    }
  }
  return null;
}

function isImportCardGroupExpanded(groupKey: string): boolean {
  return expandedImportCardGroups.value.has(groupKey);
}

function toggleImportCardGroup(groupKey: string): void {
  const next = new Set(expandedImportCardGroups.value);
  if (next.has(groupKey)) {
    next.delete(groupKey);
  } else {
    next.add(groupKey);
  }
  expandedImportCardGroups.value = next;
}

function hoverPreviewImageUrl(candidate: PreviewCandidate, preferredLanguageCode?: string): string {
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

function applyPreviewState(result: DelverLensImportPreview): void {
  const previousSelectedId = selectedEntity.value?.id ?? null;
  preview.value = result;
  importSessionId.value = result.session_id;
  localStorage.setItem(IMPORT_SESSION_STORAGE_KEY, result.session_id);
  importEntities.value = result.entities.map((entity) => ({ ...entity, cards: [...entity.cards] }));
  const nextSelectedId = result.selected_entity_id ?? previousSelectedId;
  selectedEntity.value =
    importEntities.value.find((entity) => entity.id === nextSelectedId) ?? importEntities.value[0] ?? null;
  importCompleted.value = result.status === 'completed';
}

function startHoverPreview(
  event: MouseEvent,
  candidate: PreviewCandidate | null,
  preferredLanguageCode?: string | null,
): void {
  clearHoverPreviewTimer();
  hoverPreview.value = null;
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
  if (!candidate) {
    return;
  }
  const { clientX, clientY } = event;
  const initialImageUrl = hoverPreviewImageUrl(candidate, preferredLanguageCode ?? undefined);
  const fallbackImageUrl =
    (preferredLanguageCode || candidate.language_code) === 'en'
      ? null
      : hoverPreviewImageUrl(candidate, 'en');
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

function startHoverPreviewForGroup(event: MouseEvent, group: ImportCardGroup): void {
  const candidate = importCardGroupPreviewCandidate(group);
  startHoverPreview(event, candidate, candidate?.language_code);
}

function startHoverPreviewForCard(event: MouseEvent, card: DelverLensImportCard): void {
  startHoverPreview(event, importCardPreviewCandidate(card), card.language_code);
}

function stopHoverPreview(): void {
  clearHoverPreviewTimer();
  hoverPreview.value = null;
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
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

function importCardTargetCollectionName(entity: DelverLensImportEntity): string | null {
  if (entity.target_type === 'wishdeck') {
    return null;
  }
  const value = targetCollectionValue(entity);
  if (value === 'new') {
    return entity.name;
  }
  if (value?.startsWith('existing:')) {
    const id = Number(value.split(':')[1]);
    return collections.value.find((collection) => collection.id === id)?.name ?? null;
  }
  if (value?.startsWith('import:')) {
    const id = Number(value.split(':')[1]);
    return importEntities.value.find((item) => item.id === id)?.name ?? null;
  }
  return null;
}

function importCardAttributeLine(card: DelverLensImportCard, entity: DelverLensImportEntity): string {
  if (entity.target_type === 'wishdeck') {
    return card.language ?? '';
  }
  const setLabel = card.set_code ? card.set_code.toUpperCase() : null;
  const collectorLabel = card.collector_number ? `#${card.collector_number}` : null;
  const printingLabel = [setLabel, collectorLabel].filter(Boolean).join(' ');
  return [printingLabel, card.language, card.finish, card.condition_code]
    .filter(Boolean)
    .join(' · ');
}

function attributeLabel(attribute: string): string {
  return attribute.charAt(0).toUpperCase() + attribute.slice(1);
}

function cardCompactWarnings(card: DelverLensImportCard): string[] {
  const structuredWarnings = card.attribute_changes.map(
    (change) => `${attributeLabel(change.attribute)}: ${change.before} -> ${change.after}`,
  );
  const structuredReasons = new Set(
    card.attribute_changes.map((change) => change.reason).filter((reason): reason is string => Boolean(reason)),
  );
  const plainWarnings = card.warnings.filter((warning) => !structuredReasons.has(warning));
  return [
    ...structuredWarnings,
    ...plainWarnings,
    ...[unrecognizedCardWarning(card)].filter((warning): warning is string => warning !== null),
  ];
}

function unrecognizedCardWarning(card: DelverLensImportCard): string | null {
  if (card.oracle_id && card.scryfall_id && card.printing_id !== null) {
    return null;
  }
  return `${card.name}: card is not recognized and will be ignored during import.`;
}

function entityEditPayload(entity: DelverLensImportEntity): DelverLensImportEntityEdit {
  return {
    id: entity.id,
    source_list_id: entity.source_list_id,
    target_type: entity.target_type,
    name: entity.name.trim(),
    note: entity.note,
    player_id: entity.player_id,
    created_at: entity.created_at,
    target_collection_mode: entity.target_collection_mode,
    target_collection_id: entity.target_collection_id,
    target_import_list_id: entity.target_import_list_id,
  };
}

function mergeTargetLabel(entity: DelverLensImportEntity): string {
  return `${entity.name} (${targetTypeLabel(entity.target_type)})`;
}

async function deleteSelectedImportEntity(): Promise<void> {
  const entity = selectedEntity.value;
  const sessionId = importSessionId.value;
  if (!entity || !sessionId || importCompleted.value || actionLoading.value) {
    return;
  }
  actionLoading.value = true;
  previewError.value = '';
  importMessage.value = '';
  try {
    const result = await deleteDelverLensImportEntity(sessionId, entity.id);
    applyPreviewState(result);
    importMessage.value = `${entity.name} removed from import.`;
  } catch (error) {
    previewError.value = getApiErrorMessage(error, 'Import row could not be removed');
  } finally {
    actionLoading.value = false;
  }
}

async function mergeSelectedImportEntity(): Promise<void> {
  const source = selectedEntity.value;
  const target = selectedMergeTarget.value;
  const sessionId = importSessionId.value;
  if (!source || !target || !sessionId || importCompleted.value || actionLoading.value) {
    return;
  }
  actionLoading.value = true;
  previewError.value = '';
  importMessage.value = '';
  try {
    const result = await mergeDelverLensImportEntity(sessionId, source.id, target.id, mergeSection.value);
    applyPreviewState(result);
    importMessage.value = `${source.name} merged into ${target.name}.`;
  } catch (error) {
    previewError.value = getApiErrorMessage(error, 'Import rows could not be merged');
  } finally {
    actionLoading.value = false;
  }
}

function validateImportSettings(): boolean {
  if (importInfoDirty.value) {
    previewError.value = 'Save or discard import setting changes before importing.';
    return false;
  }
  if (totalValidationErrors.value > 0) {
    previewError.value = 'Resolve import validation issues before importing.';
    return false;
  }
  return true;
}

async function applyImport(): Promise<void> {
  const sessionId = importSessionId.value;
  if (!sessionId || !canApply.value) {
    return;
  }
  applyingImport.value = true;
  previewError.value = '';
  importMessage.value = '';
  try {
    await refreshWorkspaceData();
    if (!validateImportSettings()) {
      return;
    }
    const result = await applyDelverLensImport(sessionId);
    importResult.value = result;
    const completedPreview = await getDelverLensImportSession(sessionId);
    applyPreviewState(completedPreview);
    selectedEntityDraft.value = selectedEntity.value ? importEntityDraftFromEntity(selectedEntity.value) : null;
    importMessage.value = 'Delver Lens import completed.';
    await refreshWorkspaceData();
    if (result.attribute_changes.length > 0) {
      changeDialogVisible.value = true;
    }
  } catch (error) {
    previewError.value = getApiErrorMessage(error, 'Delver Lens import failed');
  } finally {
    applyingImport.value = false;
  }
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
          <span>Import method</span>
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
          <Button
            icon="pi pi-upload"
            label="Choose .dlens"
            size="small"
            :loading="previewLoading"
            @click="chooseFile"
          />
          <div v-if="activeImportFilename" class="import-selected-file">
            <i class="pi pi-database" aria-hidden="true" />
            <div>
              <strong>{{ activeImportFilename }}</strong>
              <span>{{ activeImportFileMeta }}</span>
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

        <section class="import-stats" aria-label="Import summary">
          <div class="import-stat-row">
            <span>Entities</span>
            <strong>{{ totalRows }}</strong>
          </div>
          <div class="import-stat-row">
            <span>Cards</span>
            <strong>{{ totalCards }}</strong>
          </div>
          <div class="import-stat-row import-stat-row-warn">
            <span>Warnings</span>
            <strong>{{ totalWarnings }}</strong>
          </div>
          <div class="import-stat-row import-stat-row-error">
            <span>Errors</span>
            <strong>{{ totalValidationErrors }}</strong>
          </div>
        </section>

        <Button
          :icon="importCompleted ? 'pi pi-check-circle' : 'pi pi-check'"
          :label="importCompleted ? 'Import completed' : 'Import'"
          severity="success"
          :disabled="importCompleted || !canApply"
          :loading="applyingImport"
          @click="applyImport"
        />
      </template>
    </aside>

    <main class="inventory-pane import-preview-pane">
      <div class="workspace-heading">
        <h1>{{ activeImportFilename || 'No file selected' }}</h1>
      </div>

      <Message v-if="previewError" severity="error" size="small">
        {{ previewError }}
      </Message>
      <Message v-if="importMessage" severity="success" size="small">
        {{ importMessage }}
      </Message>

      <section v-if="!importEntities.length && !previewLoading" class="empty-state import-empty-state">
        <i class="pi pi-file-import" aria-hidden="true" />
        <span>Import preview will appear here.</span>
      </section>

      <section v-else class="import-table-panel">
        <DataTable
          v-model:selection="selectedEntity"
          :value="importEntities"
          data-key="id"
          selection-mode="single"
          striped-rows
          size="small"
        >
          <Column header="Status">
            <template #body="{ data }">
              <Message :severity="entitySeverity(data)" size="small">
                {{ entityStatusLabel(data) }}
              </Message>
            </template>
          </Column>
          <Column header="Type">
            <template #body="{ data }">
              {{ targetTypeLabel(data.target_type) }}
            </template>
          </Column>
          <Column field="name" header="Name" />
          <Column header="Owner">
            <template #body="{ data }">
              {{ playerName(data.player_id) }}
            </template>
          </Column>
          <Column header="Target collection">
            <template #body="{ data }">
              {{ entityTargetSummary(data) }}
            </template>
          </Column>
          <Column field="total_quantity" header="Qty" />
        </DataTable>
      </section>
    </main>

    <aside class="inspector-pane import-inspector-pane">
      <div class="workspace-heading">
        <h1>{{ selectedEntity ? selectedEntity.name : 'Select an import row' }}</h1>
      </div>

      <section v-if="selectedEntity" class="inspector-content">
        <Tabs v-model:value="activeInspectorTab" class="inspector-tabs">
          <TabList>
            <Tab value="info">
              {{
                selectedEntityDraft
                  ? targetTypeLabel(selectedEntityDraft.target_type)
                  : targetTypeLabel(selectedEntity.target_type)
              }}
              info
            </Tab>
            <Tab value="cards">Cards</Tab>
            <Tab v-if="!importCompleted" value="actions">Actions</Tab>
            <Tab v-if="hasSelectedIssues" value="issues">Issues ({{ selectedIssueCount }})</Tab>
          </TabList>
        </Tabs>

        <section v-if="activeInspectorTab === 'info' && selectedEntityDraft" class="import-entity-info">
          <section class="import-stats import-entity-stats" aria-label="Import entity summary">
            <div class="import-stat-row">
              <span>Source id</span>
              <strong>{{ selectedEntity.source_list_id }}</strong>
            </div>
            <div class="import-stat-row">
              <span>Source type</span>
              <strong>{{ selectedEntity.source_category_label }}</strong>
            </div>
            <div class="import-stat-row">
              <span>Quantity</span>
              <strong>{{ selectedEntity.total_quantity }}</strong>
            </div>
          </section>

          <label class="field">
            <span>Type</span>
            <Select
              :model-value="selectedEntityDraft.target_type"
              :options="TARGET_TYPE_OPTIONS"
              option-label="label"
              option-value="value"
              :disabled="importCompleted"
              @update:model-value="updateDraftTargetType(selectedEntityDraft, $event)"
            />
          </label>
          <label class="field">
            <span>Name</span>
            <InputText v-model="selectedEntityDraft.name" :disabled="importCompleted" />
          </label>
          <label class="field">
            <span>Owner</span>
            <Select
              v-model="selectedEntityDraft.player_id"
              :options="players"
              option-label="name"
              option-value="id"
              :disabled="importCompleted"
            />
          </label>
          <label v-if="selectedEntityDraft.target_type !== 'wishdeck'" class="field">
            <span>Target collection</span>
            <Select
              :model-value="normalizeTargetCollectionValue(selectedEntityDraft.target_collection_value)"
              :options="draftTargetCollectionOptions(selectedEntityDraft)"
              option-label="label"
              option-value="value"
              placeholder="Select target"
              :disabled="importCompleted"
              @update:model-value="updateDraftTargetCollection(selectedEntityDraft, $event)"
            />
          </label>
          <label class="field">
            <span>Created at</span>
            <DatePicker
              v-model="selectedEntityDraft.created_at"
              date-format="yy-mm-dd"
              hour-format="24"
              show-icon
              show-time
              :disabled="importCompleted"
            />
          </label>
          <label class="field">
            <span>Note</span>
            <Textarea v-model="selectedEntityDraft.note" rows="4" auto-resize :disabled="importCompleted" />
          </label>

          <details v-if="importInfoDirty && !importCompleted" class="unsaved-changes">
            <summary>Unsaved changes <span>Show details</span></summary>
            <div v-for="[label, saved, changed] in importInfoChanges" :key="label" class="change-row">
              <strong>{{ label }}</strong>
              <span>{{ saved || 'Empty' }}</span>
              <i class="pi pi-arrow-right" />
              <span>{{ changed || 'Empty' }}</span>
            </div>
          </details>
          <div class="panel-actions edit-actions">
            <Button
              icon="pi pi-save"
              label="Save changes"
              :disabled="!importInfoCanSave"
              @click="saveImportInfoChanges"
            />
            <Button
              label="Discard changes"
              severity="secondary"
              :disabled="!importInfoDirty || importCompleted"
              @click="discardImportInfoChanges"
            />
          </div>
        </section>

        <section v-else-if="activeInspectorTab === 'issues'" class="import-issues-list">
          <Message
            v-for="error in activeImportInfoErrors"
            :key="`error:${error}`"
            severity="error"
            size="small"
          >
            {{ error }}
          </Message>
          <Message
            v-for="warning in entityPlainWarnings(selectedEntity)"
            :key="`warning:${warning}`"
            severity="warn"
            size="small"
          >
            {{ warning }}
          </Message>
          <Message
            v-for="change in selectedEntity.attribute_changes"
            :key="`${change.source_card_id}:${change.attribute}`"
            severity="warn"
            size="small"
          >
            {{ change.card_name }}: {{ change.before }} -> {{ change.after }}
          </Message>
          <Message
            v-for="card in selectedUnrecognizedCards"
            :key="`unrecognized:${card.source_card_id}`"
            severity="warn"
            size="small"
          >
            {{ unrecognizedCardWarning(card) }}
          </Message>
          <p
            v-if="
              activeImportInfoErrors.length === 0 &&
              entityPlainWarnings(selectedEntity).length === 0 &&
              selectedEntity.attribute_changes.length === 0 &&
              selectedUnrecognizedCards.length === 0
            "
            class="empty-section"
          >
            No issues
          </p>
        </section>

        <section v-else-if="activeInspectorTab === 'actions'" class="import-actions-panel">
          <section class="import-action-block">
            <h2>Remove</h2>
            <p>Remove this collection or deck from the import preview.</p>
            <Button
              icon="pi pi-trash"
              label="Remove from import"
              severity="danger"
              :loading="actionLoading"
              :disabled="importCompleted"
              @click="deleteSelectedImportEntity"
            />
          </section>

          <section class="import-action-block">
            <h2>Merge</h2>
            <p>Combine these cards with another import item and remove the original from the preview.</p>
            <label class="field">
              <span>Target</span>
              <Select
                v-model="mergeTargetEntityId"
                :options="selectedEntityMergeTargetOptions"
                option-label="label"
                option-value="value"
                :disabled="selectedEntityMergeTargets.length === 0 || actionLoading"
              />
            </label>
            <label v-if="mergeSectionOptions.length > 0" class="field">
              <span>Section</span>
              <Select
                v-model="mergeSection"
                :options="mergeSectionOptions"
                option-label="label"
                option-value="value"
                :disabled="actionLoading"
              />
            </label>
            <Button
              label="Merge into target"
              :loading="actionLoading"
              :disabled="!canMergeSelectedEntity"
              @click="mergeSelectedImportEntity"
            >
              <template #icon>
                <span class="material-symbols-outlined import-merge-icon" aria-hidden="true">
                  merge_type
                </span>
              </template>
            </Button>
          </section>
        </section>

        <section v-else-if="activeInspectorTab === 'cards'" class="import-card-list">
          <section v-for="section in selectedImportCardSections" :key="section.key" class="decklist-section">
            <div class="section-header">
              <h2>{{ section.label }}</h2>
              <strong class="decklist-section-count">
                {{ section.groups.reduce((sum, group) => sum + group.quantity, 0) }}
              </strong>
            </div>
            <div v-if="section.groups.length" class="decklist">
              <div v-for="group in section.groups" :key="group.key" class="decklist-row-group">
                <div
                  class="decklist-row decklist-summary-row import-decklist-summary-row"
                  @pointerenter="startHoverPreviewForGroup($event, group)"
                  @pointermove="updateHoverPreviewPosition"
                  @pointerleave="stopHoverPreview"
                  @mouseenter="startHoverPreviewForGroup($event, group)"
                  @mousemove="updateHoverPreviewPosition"
                  @mouseleave="stopHoverPreview"
                >
                  <button
                    class="decklist-summary-toggle import-decklist-summary-label"
                    type="button"
                    :aria-expanded="isImportCardGroupExpanded(group.key)"
                    @click="toggleImportCardGroup(group.key)"
                  >
                    <i
                      class="pi"
                      :class="
                        isImportCardGroupExpanded(group.key) ? 'pi-chevron-down' : 'pi-chevron-right'
                      "
                      aria-hidden="true"
                    />
                    <span>{{ group.name }}</span>
                  </button>
                  <strong>{{ group.quantity }}</strong>
                </div>
                <div v-if="isImportCardGroupExpanded(group.key)" class="decklist-detail-list">
                  <div
                    v-for="card in group.cards"
                    :key="card.source_card_id"
                    class="decklist-detail-row import-card-detail-row"
                    @pointerenter="startHoverPreviewForCard($event, card)"
                    @pointermove="updateHoverPreviewPosition"
                    @pointerleave="stopHoverPreview"
                    @mouseenter="startHoverPreviewForCard($event, card)"
                    @mousemove="updateHoverPreviewPosition"
                    @mouseleave="stopHoverPreview"
                  >
                    <div>
                      <strong>{{ card.name }}</strong>
                      <span v-if="importCardTargetCollectionName(selectedEntity)">
                        {{ importCardTargetCollectionName(selectedEntity) }}
                      </span>
                      <span>{{ importCardAttributeLine(card, selectedEntity) }}</span>
                      <Message
                        v-for="warning in cardCompactWarnings(card)"
                        :key="`${card.source_card_id}:${warning}`"
                        severity="warn"
                        size="small"
                      >
                        {{ warning }}
                      </Message>
                    </div>
                    <span class="decklist-detail-quantity">{{ card.quantity }}</span>
                  </div>
                </div>
              </div>
            </div>
            <p v-else class="empty-section">No cards</p>
          </section>
        </section>
      </section>

      <section v-else class="empty-state import-empty-state">
        <i class="pi pi-list-check" aria-hidden="true" />
        <span>Select a row to inspect import details.</span>
      </section>
    </aside>

    <Dialog
      v-model:visible="changeDialogVisible"
      modal
      header="Imported card detail changes"
      class="attribute-update-dialog"
    >
      <section v-if="importResult" class="attribute-update-summary">
        <p class="attribute-update-description">
          Some card details were adjusted to match available catalog data.
        </p>
        <details
          v-for="group in importAttributeChangeGroups"
          :key="group.key"
          class="attribute-update-group"
        >
          <summary>
            <strong>{{ group.name }}</strong>
            <span>
              {{ group.cards.length }} {{ group.cards.length === 1 ? 'card' : 'cards' }} adjusted
            </span>
          </summary>
          <div class="attribute-update-card-list">
            <article v-for="card in group.cards" :key="card.key" class="attribute-update-card">
              <div class="attribute-update-card-heading">
                <strong>{{ card.name }}</strong>
                <span v-if="card.quantity > 1">x{{ card.quantity }}</span>
              </div>
              <div
                v-for="change in card.changes"
                :key="`${change.source_list_id}:${change.source_card_id}:${change.attribute}`"
                class="attribute-update-change"
              >
                <span>{{ attributeLabel(change.attribute) }}</span>
                <strong>{{ change.before }}</strong>
                <i class="pi pi-arrow-right" aria-hidden="true" />
                <strong>{{ change.after }}</strong>
              </div>
            </article>
          </div>
        </details>
      </section>
      <template #footer>
        <Button label="Close" @click="changeDialogVisible = false" />
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

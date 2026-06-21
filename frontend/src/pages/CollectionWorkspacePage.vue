<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import DatePicker from 'primevue/datepicker';
import Dialog from 'primevue/dialog';
import InputNumber from 'primevue/inputnumber';
import InputText from 'primevue/inputtext';
import ProgressSpinner from 'primevue/progressspinner';
import Select from 'primevue/select';
import Tab from 'primevue/tab';
import TabList from 'primevue/tablist';
import Tabs from 'primevue/tabs';
import Textarea from 'primevue/textarea';
import ToggleSwitch from 'primevue/toggleswitch';

import CardPrintingSelectors from '@/components/CardPrintingSelectors.vue';
import type { CardPrintingSelection } from '@/components/CardPrintingSelectors.vue';
import SearchFieldToggle from '@/components/SearchFieldToggle.vue';
import ScryfallSymbolsText from '@/components/ScryfallSymbolsText.vue';
import WorkspacePaginator from '@/components/WorkspacePaginator.vue';
import {
  addWorkspaceCollectionItem,
  ApiError,
  createWorkspaceCollection,
  deleteWorkspaceCollection,
  deleteWorkspaceCollectionItem,
  getApiErrorMessage,
  getWorkspacePrintingDetails,
  listWorkspaceCollectionItems,
  listWorkspaceCollections,
  listWorkspacePlayers,
  listWorkspacePrintings,
  suggestWorkspaceCards,
  updateWorkspaceCollectionItem,
  updateWorkspaceCollection,
} from '@/shared/api';
import type {
  CardDetails,
  CardPrinting,
  CardSuggestion,
  WorkspaceCollection,
  WorkspaceCollectionAllocationSummary,
  WorkspaceCollectionItem,
  WorkspacePlayer,
} from '@/shared/api';

const route = useRoute();
const router = useRouter();
const conditions = ['NM', 'SP', 'MP', 'HP', 'D'];
const HOVER_PREVIEW_DELAY_MS = 450;
const CARD_NORMAL_IMAGE_WIDTH = 488;
const CARD_NORMAL_IMAGE_HEIGHT = 680;
const HOVER_PREVIEW_WIDTH = Math.round(CARD_NORMAL_IMAGE_WIDTH * 0.75);
const HOVER_PREVIEW_HEIGHT = Math.round(
  HOVER_PREVIEW_WIDTH * (CARD_NORMAL_IMAGE_HEIGHT / CARD_NORMAL_IMAGE_WIDTH),
);
const INVENTORY_SEARCH_FIELD_OPTIONS = [
  { label: 'Name', value: 'name' },
  { label: 'Type', value: 'type' },
] as const;
type InventorySearchField = (typeof INVENTORY_SEARCH_FIELD_OPTIONS)[number]['value'];

type PreviewCandidate = {
  printing_id: number;
  language_code: string;
  name: string;
};

type CollectionAllocationDeckGroup = {
  deckId: number;
  deckName: string;
  sections: {
    section: string;
    quantity: number;
  }[];
};

const sidebarCollapsed = ref(false);
const activeTab = ref<'info' | 'add' | 'card' | 'edit' | 'allocations'>('info');
const collections = ref<WorkspaceCollection[]>([]);
const players = ref<WorkspacePlayer[]>([]);
const selectedCollectionId = ref<number | null>(null);
const collectionName = ref('');
const collectionPlayerId = ref<number | null>(null);
const collectionNote = ref('');
const collectionIsDefault = ref(false);
const collectionIsWishlist = ref(false);
const collectionCreatedAt = ref<Date | null>(null);
const createCollectionDialogVisible = ref(false);
const allocationRemovalDialogVisible = ref(false);
const attributeUpdateDialogVisible = ref(false);
const deleteAllocatedCardDialogVisible = ref(false);
const deleteAllocatedCollectionDialogVisible = ref(false);
const newCollectionName = ref('');
const newCollectionPlayerId = ref<number | null>(null);
const newCollectionIsWishlist = ref(false);
const createCollectionError = ref('');
const collectionSaving = ref(false);
const deleteCollectionAllocationSignature = ref('');
const deleteCollectionAllocationItems = ref<WorkspaceCollectionAllocationSummary[]>([]);
const attributeUpdateAvailableQuantity = ref(0);
const attributeUpdateAllocationDraft = ref<Record<number, number>>({});
const inventory = ref<WorkspaceCollectionItem[]>([]);
const inventoryLoading = ref(false);
const inventoryFirst = ref(0);
const inventoryRows = ref(100);
const inventorySearchQuery = ref('');
const inventorySearchField = ref<InventorySearchField>('name');
const selectedInventoryItem = ref<WorkspaceCollectionItem | null>(null);
const search = ref('');
const exactMatch = ref(false);
const suggestions = ref<CardSuggestion[]>([]);
const suggestionsOpen = ref(false);
const selectedAlias = ref<CardSuggestion | null>(null);
let inventoryRequestId = 0;

function keyruneRarityClass(rarity: string): string {
  return rarity === 'special' ? 'ss-timeshifted' : `ss-${rarity}`;
}

function allocationSectionLabel(section: string): string {
  const labels: Record<string, string> = {
    main: 'Main',
    side: 'Sideboard',
    maybe: 'Maybeboard',
    commander: 'Commander',
  };
  return labels[section] ?? section;
}

function collectionAllocationSignature(items: WorkspaceCollectionAllocationSummary[]): string {
  return items
    .flatMap((item) => item.allocations)
    .slice()
    .sort((left, right) => left.deck_item_id - right.deck_item_id)
    .map((allocation) => `${allocation.deck_item_id}:${allocation.quantity}`)
    .join('|');
}

function collectionAllocationDeckGroups(
  item: WorkspaceCollectionAllocationSummary,
): CollectionAllocationDeckGroup[] {
  const groups = new Map<number, CollectionAllocationDeckGroup>();
  item.allocations.forEach((allocation) => {
    const group = groups.get(allocation.deck_id);
    if (group) {
      const section = group.sections.find((entry) => entry.section === allocation.section);
      if (section) {
        section.quantity += allocation.quantity;
      } else {
        group.sections.push({ section: allocation.section, quantity: allocation.quantity });
      }
      return;
    }
    groups.set(allocation.deck_id, {
      deckId: allocation.deck_id,
      deckName: allocation.deck_name,
      sections: [{ section: allocation.section, quantity: allocation.quantity }],
    });
  });
  return Array.from(groups.values());
}

function isCollectionAllocationDeleteDetail(
  detail: unknown,
): detail is {
  message: string;
  allocation_signature: string;
  items: WorkspaceCollectionAllocationSummary[];
} {
  return (
    typeof detail === 'object' &&
    detail !== null &&
    'message' in detail &&
    'allocation_signature' in detail &&
    'items' in detail &&
    Array.isArray((detail as { items?: unknown }).items)
  );
}
const printings = ref<CardPrinting[]>([]);
const preferredLanguageCode = ref('');
const addSelection = ref<CardPrintingSelection | null>(null);
const condition = ref('NM');
const quantity = ref(1);
const editItem = ref<WorkspaceCollectionItem | null>(null);
const editPrintings = ref<CardPrinting[]>([]);
const editSelection = ref<CardPrintingSelection | null>(null);
const editCondition = ref('NM');
const editQuantity = ref(1);
const details = ref<CardDetails | null>(null);
const editDetails = ref<CardDetails | null>(null);
const cardInfoDetails = ref<CardDetails | null>(null);
const loadingDetails = ref(false);
const loadingEditDetails = ref(false);
const loadingCardInfo = ref(false);
const hoverPreview = ref<{
  imageUrl: string;
  fallbackImageUrl: string | null;
  label: string;
  x: number;
  y: number;
} | null>(null);
const previewImageLoading = ref(false);
const editImageLoading = ref(false);
const cardInfoImageLoading = ref(false);
const hoverPreviewLoading = ref(false);
const hoverPreviewError = ref(false);
const saving = ref(false);
const message = ref('');
const error = ref('');
const imageDialog = ref<HTMLDialogElement | null>(null);
const dialogImageUrl = ref('');
const searchContainer = ref<HTMLElement | null>(null);
const selectedFaceOrder = ref(0);
const cardInfoFaceOrder = ref(0);
let suggestTimer: number | undefined;
let suppressNextSuggestionRefresh = false;
let detailsRequestId = 0;
let editDetailsRequestId = 0;
let hoverPreviewTimer: number | null = null;
let hoverPreviewRequestId = 0;
let inventorySearchTimer: number | undefined;

const selectedCollection = computed(
  () => collections.value.find((collection) => collection.id === selectedCollectionId.value) ?? null,
);
const totalCards = computed(() => inventory.value.reduce((sum, item) => sum + item.quantity, 0));
const inventorySummaryText = computed(() =>
  inventorySearchQuery.value.trim()
    ? `${totalCards.value} matching cards`
    : `${totalCards.value} cards in collection`,
);
const filteredInventory = computed(() => inventory.value);
const paginatedInventory = computed(() =>
  filteredInventory.value.slice(inventoryFirst.value, inventoryFirst.value + inventoryRows.value),
);
const selectedPrinting = computed(() => addSelection.value?.printing ?? null);
const cardFaces = computed(() => details.value?.card.card_faces ?? []);
const selectedFace = computed(() => cardFaces.value[selectedFaceOrder.value] ?? details.value?.card);
const cardName = computed(() => selectedFace.value?.printed_name ?? selectedFace.value?.name ?? '');
const cardManaCost = computed(() => selectedFace.value?.mana_cost ?? '');
const cardText = computed(() => selectedFace.value?.printed_text ?? selectedFace.value?.oracle_text ?? '');
const cardType = computed(() => selectedFace.value?.printed_type_line ?? selectedFace.value?.type_line ?? '');
function withFaceOrder(url: string | null | undefined, faceOrder: number): string {
  return url ? `${url}${url.includes('?') ? '&' : '?'}face_order=${faceOrder}` : '';
}
const imageNormalUrl = computed(() =>
  withFaceOrder(details.value?.image_normal_url, selectedFaceOrder.value),
);
const imageNativeUrl = computed(() =>
  withFaceOrder(details.value?.image_native_url, selectedFaceOrder.value),
);
const editImageNormalUrl = computed(() => editDetails.value?.image_normal_url ?? '');
const editImageNativeUrl = computed(() => editDetails.value?.image_native_url ?? '');
const cardInfoFaces = computed(() => cardInfoDetails.value?.card.card_faces ?? []);
const cardInfoFace = computed(
  () => cardInfoFaces.value[cardInfoFaceOrder.value] ?? cardInfoDetails.value?.card,
);
const cardInfoName = computed(
  () => cardInfoFace.value?.printed_name ?? cardInfoFace.value?.name ?? selectedInventoryItem.value?.name ?? '',
);
const cardInfoManaCost = computed(() => cardInfoFace.value?.mana_cost ?? '');
const cardInfoType = computed(
  () => cardInfoFace.value?.printed_type_line ?? cardInfoFace.value?.type_line ?? '',
);
const cardInfoText = computed(
  () => cardInfoFace.value?.printed_text ?? cardInfoFace.value?.oracle_text ?? '',
);
const cardInfoFlavorText = computed(() => cardInfoFace.value?.flavor_text ?? '');
const cardInfoImageNormalUrl = computed(() =>
  withFaceOrder(cardInfoDetails.value?.image_normal_url, cardInfoFaceOrder.value),
);
const cardInfoImageNativeUrl = computed(() =>
  withFaceOrder(cardInfoDetails.value?.image_native_url, cardInfoFaceOrder.value),
);
const cardInfoStats = computed(() => {
  if (cardInfoFace.value?.power) {
    return { label: 'P/T', value: `${cardInfoFace.value.power}/${cardInfoFace.value.toughness ?? ''}` };
  }
  if (cardInfoFace.value?.loyalty) {
    return { label: 'Loyalty', value: cardInfoFace.value.loyalty };
  }
  if (cardInfoFace.value?.defense) {
    return { label: 'Defense', value: cardInfoFace.value.defense };
  }
  return null;
});
const cardInfoLegalities = computed(() =>
  Object.entries(cardInfoDetails.value?.card.legalities ?? {})
    .filter(([, legality]) => legality !== 'not_legal')
    .map(([format, legality]) => ({ format, legality })),
);
const selectedAllocationRows = computed(() => selectedInventoryItem.value?.allocations ?? []);
const selectedOwnedQuantity = computed(() => selectedInventoryItem.value?.quantity ?? 0);
const selectedAllocatedQuantity = computed(() => selectedInventoryItem.value?.allocated_quantity ?? 0);
const selectedAvailableQuantity = computed(() => selectedInventoryItem.value?.available_quantity ?? 0);
const collectionAllocatedItems = computed<WorkspaceCollectionAllocationSummary[]>(() =>
  inventory.value
    .filter((item) => item.allocated_quantity > 0)
    .map((item) => ({
      collection_item_id: item.id,
      name: item.name,
      allocations: item.allocations,
    })),
);
const editItemAllocated = computed(() => (editItem.value?.allocated_quantity ?? 0) > 0);
const allocationRemovalDraft = ref<Record<number, number>>({});
const requiredAllocationRemovals = computed(() =>
  Math.max(0, (editItem.value?.allocated_quantity ?? 0) - editQuantity.value),
);
const selectedAllocationRemovals = computed(() =>
  Object.values(allocationRemovalDraft.value).reduce((sum, value) => sum + value, 0),
);
const allocatedAfterRemovals = computed(() =>
  Math.max(0, (editItem.value?.allocated_quantity ?? 0) - requiredAllocationRemovals.value),
);
const availableAfterRemovals = computed(() => editQuantity.value - allocatedAfterRemovals.value);
const editIdentityChanged = computed(() => {
  const item = editItem.value;
  const selection = editSelection.value;
  if (!item || !selection?.printing || selection.finishId == null) {
    return false;
  }
  return (
    item.printing_id !== selection.printing.id ||
    item.finish_id !== selection.finishId ||
    item.language_code !== selection.languageCode ||
    item.condition_code !== editCondition.value
  );
});
const editQuantityChanged = computed(() => {
  const item = editItem.value;
  return Boolean(item && item.quantity !== editQuantity.value);
});
const matchingAttributeUpdateItem = computed(() => {
  const item = editItem.value;
  const selection = editSelection.value;
  if (!item || !selection?.printing || selection.finishId == null) {
    return null;
  }
  const printingId = selection.printing.id;
  const finishId = selection.finishId;
  const languageCode = selection.languageCode;
  return (
    inventory.value.find(
      (candidate) =>
        candidate.id !== item.id &&
        candidate.printing_id === printingId &&
        candidate.finish_id === finishId &&
        candidate.language_code === languageCode &&
        candidate.condition_code === editCondition.value,
    ) ?? null
  );
});
const allocationRemovalChanges = computed(() => {
  const item = editItem.value;
  if (!item) {
    return [];
  }
  return [
    ['Allocated copies', String(item.allocated_quantity), String(allocatedAfterRemovals.value)],
    ['Available copies', String(item.available_quantity), String(availableAfterRemovals.value)],
  ];
});
const selectedAttributeUpdateAllocatedQuantity = computed(() =>
  Object.values(attributeUpdateAllocationDraft.value).reduce((sum, value) => sum + value, 0),
);
const selectedAttributeUpdateQuantity = computed(
  () => attributeUpdateAvailableQuantity.value + selectedAttributeUpdateAllocatedQuantity.value,
);
const attributeUpdateValid = computed(() => selectedAttributeUpdateQuantity.value > 0);
const sourceQuantityAfterAttributeUpdate = computed(() =>
  Math.max(0, (editItem.value?.quantity ?? 0) - selectedAttributeUpdateQuantity.value),
);
const targetQuantityBeforeAttributeUpdate = computed(() => matchingAttributeUpdateItem.value?.quantity ?? 0);
const targetQuantityAfterAttributeUpdate = computed(
  () => targetQuantityBeforeAttributeUpdate.value + selectedAttributeUpdateQuantity.value,
);
const attributeUpdateAllocationPayload = computed(() =>
  Object.entries(attributeUpdateAllocationDraft.value)
    .map(([deckItemId, quantity]) => ({ deck_item_id: Number(deckItemId), quantity }))
    .filter((selection) => selection.quantity > 0),
);
const currentCardDetailsLabel = computed(() => {
  const item = editItem.value;
  if (!item) {
    return '';
  }
  return `${item.set_code.toUpperCase()} #${item.collector_number} · ${item.language_code.toUpperCase()} · ${item.finish} · ${item.condition_code}`;
});
const updatedCardDetailsLabel = computed(() => {
  const selection = editSelection.value;
  if (!selection?.printing) {
    return '';
  }
  return `${selection.setCode.toUpperCase()} #${selection.collectorNumber} · ${selection.languageCode.toUpperCase()} · ${selection.finish} · ${editCondition.value}`;
});
const attributeUpdateChanges = computed(() => {
  const item = editItem.value;
  if (!item) {
    return [];
  }
  return [
    [
      'Current cards',
      currentCardDetailsLabel.value,
      String(item.quantity),
      String(sourceQuantityAfterAttributeUpdate.value),
    ],
    [
      matchingAttributeUpdateItem.value ? 'Matching cards' : 'Updated cards',
      updatedCardDetailsLabel.value,
      String(targetQuantityBeforeAttributeUpdate.value),
      String(targetQuantityAfterAttributeUpdate.value),
    ],
  ];
});
const allocationRemovalValid = computed(
  () =>
    requiredAllocationRemovals.value > 0 &&
    selectedAllocationRemovals.value === requiredAllocationRemovals.value,
);
const allocationRemovalPayload = computed(() =>
  Object.entries(allocationRemovalDraft.value)
    .map(([deckItemId, quantity]) => ({ deck_item_id: Number(deckItemId), quantity }))
    .filter((removal) => removal.quantity > 0),
);
const hoverPreviewStyle = computed(() => {
  if (!hoverPreview.value) {
    return {};
  }
  const gap = 14;
  const viewportPadding = 12;
  const maxLeft = Math.max(viewportPadding, window.innerWidth - HOVER_PREVIEW_WIDTH - viewportPadding);
  const maxTop = Math.max(viewportPadding, window.innerHeight - HOVER_PREVIEW_HEIGHT - viewportPadding);
  const cursorLeft = hoverPreview.value.x + gap;
  const cursorTop = hoverPreview.value.y + gap;
  const fallbackLeft =
    cursorLeft + HOVER_PREVIEW_WIDTH <= window.innerWidth - viewportPadding
      ? cursorLeft
      : hoverPreview.value.x - HOVER_PREVIEW_WIDTH - gap;
  const fallbackTop =
    cursorTop + HOVER_PREVIEW_HEIGHT <= window.innerHeight - viewportPadding
      ? cursorTop
      : hoverPreview.value.y - HOVER_PREVIEW_HEIGHT - gap;
  return {
    left: `${Math.min(Math.max(viewportPadding, fallbackLeft), maxLeft)}px`,
    top: `${Math.min(Math.max(viewportPadding, fallbackTop), maxTop)}px`,
  };
});
const editChanges = computed(() => {
  const item = editItem.value;
  const selection = editSelection.value;
  if (!item) {
    return [];
  }
  if (!selection) {
    return [];
  }
  return [
    ['Set', item.set_code, selection.setCode],
    ['Collector #', item.collector_number, selection.collectorNumber],
    ['Language', item.language, selection.language],
    ['Finish', item.finish, selection.finish],
    ['Condition', item.condition_code, editCondition.value],
    ['Quantity', String(item.quantity), String(editQuantity.value)],
  ].filter(([, saved, changed]) => saved !== changed);
});
const editDirty = computed(() => editChanges.value.length > 0);
const editActionError = computed(() => (activeTab.value === 'edit' ? error.value : ''));
const collectionCreatedAtTimestamp = computed(() =>
  collectionCreatedAt.value ? Math.floor(collectionCreatedAt.value.getTime() / 1000) : null,
);

function timestampToDate(timestamp: number | null | undefined): Date | null {
  return typeof timestamp === 'number' ? new Date(timestamp * 1000) : null;
}

function formatCollectionDate(timestamp: number | null | undefined): string {
  if (typeof timestamp !== 'number') {
    return '';
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp * 1000));
}

const collectionChanges = computed(() => {
  const collection = selectedCollection.value;
  if (!collection) {
    return [];
  }
  const ownerName = (playerId: number | null) =>
    players.value.find((player) => player.id === playerId)?.name ?? '';
  return [
    ['Name', collection.name, collectionName.value],
    ['Owner', ownerName(collection.player_id), ownerName(collectionPlayerId.value)],
    ['Created at', formatCollectionDate(collection.created_at), formatCollectionDate(collectionCreatedAtTimestamp.value)],
    ['Primary collection', collection.is_default ? 'Yes' : 'No', collectionIsDefault.value ? 'Yes' : 'No'],
    ['Wishlist', collection.is_wishlist ? 'Yes' : 'No', collectionIsWishlist.value ? 'Yes' : 'No'],
    ['Note', collection.note ?? '', collectionNote.value],
  ].filter(([, saved, changed]) => saved !== changed);
});
const collectionDirty = computed(() => collectionChanges.value.length > 0);
const collectionCanSave = computed(() =>
  collectionDirty.value &&
  collectionCreatedAtTimestamp.value !== null &&
  Boolean(collectionName.value.trim()),
);

function resetCollectionDraft(): void {
  const collection = selectedCollection.value;
  collectionName.value = collection?.name ?? '';
  collectionPlayerId.value = collection?.player_id ?? null;
  collectionNote.value = collection?.note ?? '';
  collectionIsDefault.value = collection?.is_default ?? false;
  collectionIsWishlist.value = collection?.is_wishlist ?? false;
  collectionCreatedAt.value = timestampToDate(collection?.created_at);
}

function collectionIdFromRoute(): number | null {
  const rawCollectionId = route.query.collection_id;
  const collectionId = Array.isArray(rawCollectionId) ? rawCollectionId[0] : rawCollectionId;
  const parsedCollectionId = Number(collectionId);
  return Number.isInteger(parsedCollectionId) && parsedCollectionId > 0 ? parsedCollectionId : null;
}

function replaceCollectionRoute(collectionId: number | null): void {
  const nextQuery = { ...route.query };
  if (collectionId === null) {
    delete nextQuery.collection_id;
  } else {
    nextQuery.collection_id = String(collectionId);
  }
  void router.replace({ path: '/', query: nextQuery });
}

function getInitialCollectionId(): number | null {
  const routeCollectionId = collectionIdFromRoute();
  if (routeCollectionId && collections.value.some((collection) => collection.id === routeCollectionId)) {
    return routeCollectionId;
  }
  return collections.value.find((collection) => collection.is_default)?.id ?? collections.value[0]?.id ?? null;
}

function selectCollection(collectionId: number, syncRoute = true): void {
  if (
    selectedCollectionId.value !== collectionId &&
    collectionDirty.value &&
    !window.confirm('Discard unsaved collection changes?')
  ) {
    return;
  }
  selectedCollectionId.value = collectionId;
  activeTab.value = 'info';
  error.value = '';
  message.value = '';
  if (syncRoute) {
    replaceCollectionRoute(collectionId);
  }
}

function openCreateCollectionDialog(): void {
  if (collectionDirty.value && !window.confirm('Discard unsaved collection changes?')) {
    return;
  }
  newCollectionName.value = '';
  newCollectionPlayerId.value =
    players.value.find((player) => player.is_default)?.id ?? players.value[0]?.id ?? null;
  newCollectionIsWishlist.value = false;
  createCollectionError.value = '';
  createCollectionDialogVisible.value = true;
}

async function createCollection(): Promise<void> {
  if (!newCollectionName.value.trim() || newCollectionPlayerId.value === null) {
    return;
  }
  collectionSaving.value = true;
  createCollectionError.value = '';
  error.value = '';
  try {
    const created = await createWorkspaceCollection({
      name: newCollectionName.value.trim(),
      player_id: newCollectionPlayerId.value,
      note: null,
      is_default: false,
      is_wishlist: newCollectionIsWishlist.value,
    });
    collections.value = await listWorkspaceCollections();
    selectedCollectionId.value = created.id;
    replaceCollectionRoute(created.id);
    activeTab.value = 'info';
    createCollectionDialogVisible.value = false;
    createCollectionError.value = '';
    message.value = 'Collection created';
  } catch (requestError) {
    createCollectionError.value = getApiErrorMessage(requestError, 'Collection could not be created');
  } finally {
    collectionSaving.value = false;
  }
}

async function saveCollectionChanges(): Promise<void> {
  const collection = selectedCollection.value;
  if (
    !collection ||
    collectionPlayerId.value === null ||
    collectionCreatedAtTimestamp.value === null ||
    !collectionName.value.trim() ||
    !collectionDirty.value
  ) {
    return;
  }
  collectionSaving.value = true;
  error.value = '';
  message.value = '';
  try {
    const updated = await updateWorkspaceCollection(collection.id, {
      name: collectionName.value.trim(),
      player_id: collectionPlayerId.value,
      note: collectionNote.value.trim() || null,
      is_default: collectionIsDefault.value,
      is_wishlist: collectionIsWishlist.value,
      created_at: collectionCreatedAtTimestamp.value,
    });
    collections.value = await listWorkspaceCollections();
    selectedCollectionId.value = updated.id;
    replaceCollectionRoute(updated.id);
    resetCollectionDraft();
    message.value = 'Collection changes saved';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Collection changes could not be saved');
  } finally {
    collectionSaving.value = false;
  }
}

async function deleteCollection(): Promise<void> {
  const collection = selectedCollection.value;
  if (!collection) {
    return;
  }
  if (collectionAllocatedItems.value.length > 0) {
    deleteCollectionAllocationItems.value = collectionAllocatedItems.value;
    deleteCollectionAllocationSignature.value = collectionAllocationSignature(collectionAllocatedItems.value);
    deleteAllocatedCollectionDialogVisible.value = true;
    return;
  }
  if (!window.confirm(`Delete ${collection.name} and all cards stored in it?`)) {
    return;
  }
  collectionSaving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspaceCollection(collection.id);
    collections.value = await listWorkspaceCollections();
    selectedCollectionId.value =
      collections.value.find((item) => item.is_default)?.id ?? collections.value[0]?.id ?? null;
    replaceCollectionRoute(selectedCollectionId.value);
    activeTab.value = 'info';
    message.value = 'Collection deleted';
  } catch (requestError) {
    if (requestError instanceof ApiError && isCollectionAllocationDeleteDetail(requestError.detail)) {
      deleteCollectionAllocationItems.value = requestError.detail.items;
      deleteCollectionAllocationSignature.value = requestError.detail.allocation_signature;
      deleteAllocatedCollectionDialogVisible.value = true;
    } else {
      error.value = getApiErrorMessage(requestError, 'Collection could not be deleted');
    }
  } finally {
    collectionSaving.value = false;
  }
}

async function confirmDeleteAllocatedCollection(): Promise<void> {
  const collection = selectedCollection.value;
  if (!collection) {
    return;
  }
  collectionSaving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspaceCollection(collection.id, {
      remove_allocations: true,
      allocation_signature: deleteCollectionAllocationSignature.value,
    });
    deleteAllocatedCollectionDialogVisible.value = false;
    deleteCollectionAllocationItems.value = [];
    deleteCollectionAllocationSignature.value = '';
    collections.value = await listWorkspaceCollections();
    selectedCollectionId.value =
      collections.value.find((item) => item.is_default)?.id ?? collections.value[0]?.id ?? null;
    replaceCollectionRoute(selectedCollectionId.value);
    activeTab.value = 'info';
    message.value = 'Collection deleted';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Collection could not be deleted');
  } finally {
    collectionSaving.value = false;
  }
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
    preferredLanguageCode.value = options.preferred_language_code;
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

function clearCardSearch(): void {
  if (suggestTimer !== undefined) {
    window.clearTimeout(suggestTimer);
  }
  suppressNextSuggestionRefresh = Boolean(search.value);
  search.value = '';
  suggestions.value = [];
  suggestionsOpen.value = false;
  selectedAlias.value = null;
  printings.value = [];
  preferredLanguageCode.value = '';
  addSelection.value = null;
  details.value = null;
  detailsRequestId += 1;
  selectedFaceOrder.value = 0;
  message.value = '';
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
  const requestId = ++detailsRequestId;
  if (!selectedPrinting.value) {
    details.value = null;
    return;
  }
  loadingDetails.value = true;
  selectedFaceOrder.value = 0;
  error.value = '';
  try {
    const nextDetails = await getWorkspacePrintingDetails(
      selectedPrinting.value.id,
      addSelection.value?.languageCode,
    );
    if (requestId === detailsRequestId) {
      details.value = nextDetails;
    }
  } catch (requestError) {
    if (requestId !== detailsRequestId) {
      return;
    }
    details.value = null;
    error.value = getApiErrorMessage(requestError, 'Card preview is unavailable');
  } finally {
    if (requestId === detailsRequestId) {
      loadingDetails.value = false;
    }
  }
}

async function refreshEditDetails(): Promise<void> {
  const requestId = ++editDetailsRequestId;
  const selection = editSelection.value;
  if (!selection?.printing) {
    editDetails.value = null;
    return;
  }
  loadingEditDetails.value = true;
  error.value = '';
  try {
    const nextDetails = await getWorkspacePrintingDetails(
      selection.printing.id,
      selection.languageCode,
    );
    if (requestId === editDetailsRequestId) {
      editDetails.value = nextDetails;
    }
  } catch (requestError) {
    if (requestId !== editDetailsRequestId) {
      return;
    }
    editDetails.value = null;
    error.value = getApiErrorMessage(requestError, 'Card preview is unavailable');
  } finally {
    if (requestId === editDetailsRequestId) {
      loadingEditDetails.value = false;
    }
  }
}

function pageInventory(event: { first: number; rows: number }): void {
  stopHoverPreview();
  inventoryFirst.value = event.first;
  inventoryRows.value = event.rows;
}

function selectInventorySearchField(field: string): void {
  inventorySearchField.value = field as InventorySearchField;
  inventoryFirst.value = 0;
}

function clearInventorySearch(): void {
  inventorySearchQuery.value = '';
  inventorySearchField.value = 'name';
  inventoryFirst.value = 0;
}

function clampInventoryPage(): void {
  if (filteredInventory.value.length === 0) {
    inventoryFirst.value = 0;
    return;
  }
  if (inventoryFirst.value >= filteredInventory.value.length) {
    inventoryFirst.value =
      Math.floor((filteredInventory.value.length - 1) / inventoryRows.value) * inventoryRows.value;
  }
}

function inventoryItemPreviewCandidate(item: WorkspaceCollectionItem): PreviewCandidate {
  return {
    printing_id: item.printing_id,
    language_code: item.language_code,
    name: item.name,
  };
}

function imageUrl(candidate: PreviewCandidate, preferredLanguageCode?: string): string {
  const languageCode = preferredLanguageCode || candidate.language_code;
  const params = new URLSearchParams({
    language_code: languageCode,
    preview_request: String(++hoverPreviewRequestId),
  });
  return `/api/workspace/printings/${candidate.printing_id}/images/normal?${params.toString()}`;
}

function rowFromMouseEvent(event: MouseEvent): HTMLTableRowElement | null {
  return event.target instanceof Element
    ? event.target.closest<HTMLTableRowElement>('tr[data-p-index]')
    : null;
}

function inventoryItemFromRow(row: HTMLTableRowElement | null): WorkspaceCollectionItem | null {
  const index = Number(row?.dataset.pIndex);
  return Number.isInteger(index) ? paginatedInventory.value[index] ?? null : null;
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

function startHoverPreview(event: MouseEvent, item: WorkspaceCollectionItem | null): void {
  clearHoverPreviewTimer();
  hoverPreview.value = null;
  hoverPreviewLoading.value = false;
  hoverPreviewError.value = false;
  if (!item) {
    return;
  }
  const candidate = inventoryItemPreviewCandidate(item);
  const { clientX, clientY } = event;
  const initialImageUrl = imageUrl(candidate);
  const fallbackImageUrl = candidate.language_code === 'en' ? null : imageUrl(candidate, 'en');
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

function handleInventoryPointerOver(event: MouseEvent): void {
  const row = rowFromMouseEvent(event);
  if (
    row &&
    event.relatedTarget instanceof Node &&
    row.contains(event.relatedTarget)
  ) {
    return;
  }
  startHoverPreview(event, inventoryItemFromRow(row));
}

function handleInventoryPointerOut(event: MouseEvent): void {
  const row = rowFromMouseEvent(event);
  if (
    row &&
    event.relatedTarget instanceof Node &&
    row.contains(event.relatedTarget)
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

async function loadInventory(resetPage = false): Promise<void> {
  if (resetPage) {
    inventoryFirst.value = 0;
  }
  const collectionId = selectedCollectionId.value;
  const searchQuery = inventorySearchQuery.value;
  const searchField = inventorySearchField.value;
  const requestId = (inventoryRequestId += 1);
  if (collectionId === null) {
    inventory.value = [];
    inventoryLoading.value = false;
    return;
  }
  inventoryLoading.value = true;
  try {
    const items = await listWorkspaceCollectionItems(collectionId, {
      query: searchQuery,
      searchField,
    });
    if (
      requestId !== inventoryRequestId ||
      selectedCollectionId.value !== collectionId ||
      inventorySearchQuery.value !== searchQuery ||
      inventorySearchField.value !== searchField
    ) {
      return;
    }
    inventory.value = items;
    clampInventoryPage();
  } catch (requestError) {
    if (
      requestId !== inventoryRequestId ||
      selectedCollectionId.value !== collectionId ||
      inventorySearchQuery.value !== searchQuery ||
      inventorySearchField.value !== searchField
    ) {
      return;
    }
    error.value = getApiErrorMessage(requestError, 'Collection items are unavailable');
  } finally {
    if (
      requestId === inventoryRequestId &&
      selectedCollectionId.value === collectionId &&
      inventorySearchQuery.value === searchQuery &&
      inventorySearchField.value === searchField
    ) {
      inventoryLoading.value = false;
    }
  }
}

async function refreshInventory(resetPage = false): Promise<void> {
  stopHoverPreview();
  selectedInventoryItem.value = null;
  editItem.value = null;
  editPrintings.value = [];
  editSelection.value = null;
  editDetails.value = null;
  editDetailsRequestId += 1;
  cardInfoDetails.value = null;
  if (activeTab.value === 'card' || activeTab.value === 'edit' || activeTab.value === 'allocations') {
    activeTab.value = 'info';
  }
  await loadInventory(resetPage);
}

async function selectInventoryItem(
  item: WorkspaceCollectionItem,
  nextActiveTab: 'card' | 'edit' | 'allocations' = 'card',
  skipUnsavedPrompt = false,
): Promise<void> {
  if (
    !skipUnsavedPrompt &&
    editDirty.value &&
    editItem.value?.id !== item.id &&
    !window.confirm('Discard unsaved changes?')
  ) {
    selectedInventoryItem.value = editItem.value;
    return;
  }
  selectedInventoryItem.value = item;
  editItem.value = item;
  editCondition.value = item.condition_code;
  editQuantity.value = item.quantity;
  editSelection.value = null;
  editDetails.value = null;
  editDetailsRequestId += 1;
  message.value = '';
  activeTab.value = nextActiveTab;
  loadingCardInfo.value = true;
  cardInfoFaceOrder.value = 0;
  error.value = '';
  try {
    const options = await listWorkspacePrintings(item.oracle_id, item.language_code);
    editPrintings.value = options.printings;
    cardInfoDetails.value = await getWorkspacePrintingDetails(item.printing_id, item.language_code);
  } catch (requestError) {
    cardInfoDetails.value = null;
    error.value = getApiErrorMessage(requestError, 'Card info is unavailable');
  } finally {
    loadingCardInfo.value = false;
  }
}

async function addCard(): Promise<void> {
  if (
    selectedCollectionId.value === null ||
    !selectedPrinting.value ||
    addSelection.value?.finishId == null
  ) {
    return;
  }
  detailsRequestId += 1;
  loadingDetails.value = false;
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await addWorkspaceCollectionItem(selectedCollectionId.value, {
      printing_id: selectedPrinting.value.id,
      finish_id: addSelection.value.finishId,
      language_code: addSelection.value.languageCode,
      condition_code: condition.value,
      quantity: quantity.value,
    });
    await refreshInventory(true);
    message.value = `Added to ${selectedCollection.value?.name ?? 'collection'}`;
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card could not be added');
  } finally {
    saving.value = false;
  }
}

function discardEditChanges(): void {
  const item = editItem.value;
  if (!item) {
    return;
  }
  editCondition.value = item.condition_code;
  editQuantity.value = item.quantity;
  editSelection.value = null;
  editPrintings.value = [...editPrintings.value];
  allocationRemovalDialogVisible.value = false;
  allocationRemovalDraft.value = {};
  attributeUpdateDialogVisible.value = false;
  resetAttributeUpdateDraft();
}

function resetAllocationRemovalDraft(): void {
  const item = editItem.value;
  allocationRemovalDraft.value = Object.fromEntries(
    (item?.allocations ?? []).map((allocation) => [allocation.deck_item_id, 0]),
  );
}

function allocationSignature(allocations: WorkspaceCollectionItem['allocations']): string {
  return allocations
    .slice()
    .sort((left, right) => left.deck_item_id - right.deck_item_id)
    .map((allocation) => `${allocation.deck_item_id}:${allocation.quantity}`)
    .join('|');
}

function allocationRemovalQuantity(deckItemId: number): number {
  return allocationRemovalDraft.value[deckItemId] ?? 0;
}

function allocationRemovalMax(deckItemId: number, allocationQuantity: number): number {
  const currentQuantity = allocationRemovalQuantity(deckItemId);
  const maxForCurrentRow = Math.max(
    0,
    requiredAllocationRemovals.value - (selectedAllocationRemovals.value - currentQuantity),
  );
  return Math.min(allocationQuantity, maxForCurrentRow);
}

function setAllocationRemovalQuantity(deckItemId: number, value: number | null): void {
  const allocation = editItem.value?.allocations.find(
    (entry) => entry.deck_item_id === deckItemId,
  );
  const maxQuantity = allocation ? allocationRemovalMax(deckItemId, allocation.quantity) : 0;
  allocationRemovalDraft.value = {
    ...allocationRemovalDraft.value,
    [deckItemId]: Math.min(maxQuantity, Math.max(0, value ?? 0)),
  };
}

function resetAttributeUpdateDraft(): void {
  const item = editItem.value;
  attributeUpdateAvailableQuantity.value = 0;
  attributeUpdateAllocationDraft.value = Object.fromEntries(
    (item?.allocations ?? []).map((allocation) => [allocation.deck_item_id, 0]),
  );
}

function attributeUpdateAllocatedQuantity(deckItemId: number): number {
  return attributeUpdateAllocationDraft.value[deckItemId] ?? 0;
}

function attributeUpdateRowMax(currentQuantity: number, rowQuantity: number): number {
  const itemQuantity = editItem.value?.quantity ?? 0;
  const maxForCurrentRow = Math.max(
    0,
    itemQuantity - (selectedAttributeUpdateQuantity.value - currentQuantity),
  );
  return Math.min(rowQuantity, maxForCurrentRow);
}

function attributeUpdateAvailableMax(): number {
  const item = editItem.value;
  return attributeUpdateRowMax(attributeUpdateAvailableQuantity.value, item?.available_quantity ?? 0);
}

function attributeUpdateAllocationMax(deckItemId: number, allocationQuantity: number): number {
  return attributeUpdateRowMax(attributeUpdateAllocatedQuantity(deckItemId), allocationQuantity);
}

function setAttributeUpdateAvailableQuantity(value: number | null): void {
  attributeUpdateAvailableQuantity.value = Math.min(
    attributeUpdateAvailableMax(),
    Math.max(0, value ?? 0),
  );
}

function setAttributeUpdateAllocatedQuantity(deckItemId: number, value: number | null): void {
  const allocation = editItem.value?.allocations.find(
    (entry) => entry.deck_item_id === deckItemId,
  );
  const maxQuantity = allocation ? attributeUpdateAllocationMax(deckItemId, allocation.quantity) : 0;
  attributeUpdateAllocationDraft.value = {
    ...attributeUpdateAllocationDraft.value,
    [deckItemId]: Math.min(maxQuantity, Math.max(0, value ?? 0)),
  };
}

async function saveCardChangesWithRemovals(
  allocationRemovals: { deck_item_id: number; quantity: number }[] = [],
): Promise<void> {
  const item = editItem.value;
  const selection = editSelection.value;
  if (
    selectedCollectionId.value === null ||
    !item ||
    !editDirty.value
  ) {
    return;
  }
  const payload = editItemAllocated.value
    ? {
        printing_id: item.printing_id,
        finish_id: item.finish_id,
        language_code: item.language_code,
        condition_code: item.condition_code,
        quantity: editQuantity.value,
        allocation_removals: allocationRemovals,
      }
    : selection?.printing && selection.finishId != null
      ? {
          printing_id: selection.printing.id,
          finish_id: selection.finishId,
          language_code: selection.languageCode,
          condition_code: editCondition.value,
          quantity: editQuantity.value,
          allocation_removals: allocationRemovals,
        }
      : null;
  if (!payload) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    const updated = await updateWorkspaceCollectionItem(selectedCollectionId.value, item.id, payload);
    await loadInventory();
    const refreshedItem = inventory.value.find((inventoryItem) => inventoryItem.id === updated.id) ?? updated;
    await selectInventoryItem(refreshedItem, 'edit', true);
    allocationRemovalDialogVisible.value = false;
    allocationRemovalDraft.value = {};
    activeTab.value = 'edit';
    message.value = 'Changes saved';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card changes could not be saved');
  } finally {
    saving.value = false;
  }
}

async function saveCardChanges(): Promise<void> {
  const item = editItem.value;
  if (!item || !editDirty.value) {
    return;
  }
  if (editIdentityChanged.value && editQuantityChanged.value) {
    error.value = 'Save quantity changes separately before changing card attributes.';
    return;
  }
  if (editIdentityChanged.value) {
    resetAttributeUpdateDraft();
    attributeUpdateDialogVisible.value = true;
    return;
  }
  if (editItemAllocated.value && editQuantity.value < item.allocated_quantity) {
    resetAllocationRemovalDraft();
    allocationRemovalDialogVisible.value = true;
    return;
  }
  await saveCardChangesWithRemovals();
}

async function confirmAttributeUpdate(): Promise<void> {
  const item = editItem.value;
  const selection = editSelection.value;
  if (
    selectedCollectionId.value === null ||
    !item ||
    !selection?.printing ||
    selection.finishId == null ||
    !attributeUpdateValid.value
  ) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    const updated = await updateWorkspaceCollectionItem(selectedCollectionId.value, item.id, {
      printing_id: selection.printing.id,
      finish_id: selection.finishId,
      language_code: selection.languageCode,
      condition_code: editCondition.value,
      quantity: item.quantity,
      attribute_update: {
        available_quantity: attributeUpdateAvailableQuantity.value,
        allocation_selections: attributeUpdateAllocationPayload.value,
        source_quantity: item.quantity,
        allocation_signature: allocationSignature(item.allocations),
      },
    });
    await loadInventory();
    const refreshedItem = inventory.value.find((inventoryItem) => inventoryItem.id === updated.id) ?? updated;
    await selectInventoryItem(refreshedItem, 'edit', true);
    attributeUpdateDialogVisible.value = false;
    resetAttributeUpdateDraft();
    message.value = 'Changes saved';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card changes could not be saved');
  } finally {
    saving.value = false;
  }
}

async function confirmAllocationRemovalSave(): Promise<void> {
  if (!allocationRemovalValid.value) {
    return;
  }
  await saveCardChangesWithRemovals(allocationRemovalPayload.value);
}

async function deleteCard(): Promise<void> {
  const item = editItem.value;
  if (
    selectedCollectionId.value === null ||
    !item
  ) {
    return;
  }
  if (item.allocated_quantity > 0) {
    deleteAllocatedCardDialogVisible.value = true;
    return;
  }
  if (!window.confirm(`Delete ${item.name} from this collection?`)) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspaceCollectionItem(selectedCollectionId.value, item.id);
    await refreshInventory();
    activeTab.value = 'info';
    message.value = 'Card deleted';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card could not be deleted');
  } finally {
    saving.value = false;
  }
}

async function confirmDeleteAllocatedCard(): Promise<void> {
  const item = editItem.value;
  if (selectedCollectionId.value === null || !item) {
    return;
  }
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    await deleteWorkspaceCollectionItem(selectedCollectionId.value, item.id, {
      remove_allocations: true,
    });
    deleteAllocatedCardDialogVisible.value = false;
    await refreshInventory();
    activeTab.value = 'info';
    message.value = 'Card deleted';
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Card could not be deleted');
  } finally {
    saving.value = false;
  }
}

function openImageDialog(url: string): void {
  if (url) {
    dialogImageUrl.value = url;
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

watch(
  selectedCollectionId,
  (collectionId, previousCollectionId) => {
    inventoryRequestId += 1;
    if (collectionId !== previousCollectionId) {
      inventory.value = [];
      inventoryLoading.value = collectionId !== null;
    }
    void refreshInventory(true);
  },
  { flush: 'sync' },
);
watch(selectedCollectionId, resetCollectionDraft);

watch([inventorySearchQuery, inventorySearchField], () => {
  inventoryRequestId += 1;
  inventoryFirst.value = 0;
  inventoryLoading.value = selectedCollectionId.value !== null;
  if (inventorySearchTimer !== undefined) {
    window.clearTimeout(inventorySearchTimer);
  }
  inventorySearchTimer = window.setTimeout(() => {
    void loadInventory(true);
  }, 180);
});

watch([filteredInventory, inventoryRows], clampInventoryPage);

watch(
  () => route.query.collection_id,
  () => {
    const routeCollectionId = collectionIdFromRoute();
    if (
      routeCollectionId &&
      routeCollectionId !== selectedCollectionId.value &&
      collections.value.some((collection) => collection.id === routeCollectionId)
    ) {
      selectCollection(routeCollectionId, false);
    }
  },
);

watch(imageNormalUrl, (url) => {
  previewImageLoading.value = Boolean(url);
});

watch(cardInfoImageNormalUrl, (url) => {
  cardInfoImageLoading.value = Boolean(url);
});

watch(editImageNormalUrl, (url) => {
  editImageLoading.value = Boolean(url);
});

watch(addSelection, () => {
  void refreshDetails();
});

watch(editSelection, () => {
  void refreshEditDetails();
});

onMounted(async () => {
  document.addEventListener('click', handleDocumentClick);
  players.value = await listWorkspacePlayers();
  collections.value = await listWorkspaceCollections();
  selectedCollectionId.value = getInitialCollectionId();
});

onUnmounted(() => {
  stopHoverPreview();
  if (inventorySearchTimer !== undefined) {
    window.clearTimeout(inventorySearchTimer);
  }
  document.removeEventListener('click', handleDocumentClick);
});
</script>

<template>
  <section class="collection-workspace" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
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
            @click="selectCollection(collection.id)"
          >
            <span>{{ collection.name }}</span>
            <span class="sidebar-item-icons">
              <i v-if="collection.is_default" class="pi pi-star-fill" title="Primary collection" />
              <i v-if="collection.is_wishlist" class="pi pi-shopping-cart" title="Wishlist" />
            </span>
          </button>
        </div>
        <div class="sidebar-actions">
          <Button icon="pi pi-plus" label="Add" size="small" @click="openCreateCollectionDialog" />
          <Button icon="pi pi-trash" label="Delete" size="small" severity="danger" @click="deleteCollection" />
        </div>
      </template>
    </aside>

    <main class="inventory-pane">
      <div class="workspace-heading">
        <h1>{{ selectedCollection?.name ?? 'Collection' }}</h1>
        <p>{{ inventorySummaryText }}</p>
      </div>
      <div class="inventory-search-row">
        <InputText
          v-model="inventorySearchQuery"
          class="inventory-search-input"
          :placeholder="`Search by ${inventorySearchField}`"
        />
        <SearchFieldToggle
          :model-value="inventorySearchField"
          :options="INVENTORY_SEARCH_FIELD_OPTIONS"
          @update:model-value="selectInventorySearchField"
        />
        <Button
          icon="pi pi-times"
          size="small"
          severity="secondary"
          text
          rounded
          aria-label="Clear collection search"
          title="Clear collection search"
          :disabled="!inventorySearchQuery && inventorySearchField === 'name'"
          @click="clearInventorySearch"
        />
      </div>
      <div
        class="inventory-table-wrap"
        @pointerover="handleInventoryPointerOver"
        @pointermove="updateHoverPreviewPosition"
        @pointerout="handleInventoryPointerOut"
        @mouseover="handleInventoryPointerOver"
        @mousemove="updateHoverPreviewPosition"
        @mouseout="handleInventoryPointerOut"
      >
      <DataTable
        v-model:selection="selectedInventoryItem"
        :value="paginatedInventory"
        class="inventory-table"
        data-key="id"
        selection-mode="single"
        :meta-key-selection="false"
        :loading="inventoryLoading"
        striped-rows
        @row-select="selectInventoryItem($event.data)"
      >
        <template #empty>
          {{ inventorySearchQuery ? 'No cards match this search.' : 'No cards in this collection.' }}
        </template>
        <Column field="quantity" header="Qty" />
        <Column field="available_quantity" header="Avail.">
          <template #body="{ data }">
            <span :title="data.allocated_quantity > 0 ? `${data.allocated_quantity} allocated to decks` : undefined">
              {{ data.available_quantity }}
            </span>
          </template>
        </Column>
        <Column field="name" header="Name" />
        <Column field="set_code" header="Set">
          <template #body="{ data }">
            <i
              :class="['ss', `ss-${data.keyrune_code.toLowerCase()}`, keyruneRarityClass(data.rarity)]"
              :title="`${data.set_code} · ${data.rarity}`"
              :aria-label="`${data.set_code} ${data.rarity}`"
            />
          </template>
        </Column>
        <Column header="Details" body-class="inventory-details-cell">
          <template #body="{ data }">
            #{{ data.collector_number }} · {{ data.language_code.toUpperCase() }} · {{ data.finish }} ·
            {{ data.condition_code }}
          </template>
        </Column>
        <Column field="mana_cost" header="Cost">
          <template #body="{ data }">
            <ScryfallSymbolsText v-if="data.mana_cost" :text="data.mana_cost" />
            <template v-else>—</template>
          </template>
        </Column>
      </DataTable>
      </div>
      <WorkspacePaginator
        v-if="filteredInventory.length > inventoryRows"
        class="workspace-paginator"
        :first="inventoryFirst"
        :rows="inventoryRows"
        :total-records="filteredInventory.length"
        @page="pageInventory"
      />
    </main>

    <aside class="inspector-pane">
      <div class="inspector-tab-groups">
        <Tabs v-model:value="activeTab" class="inspector-tabs">
          <TabList>
            <Tab value="info">Collection info</Tab>
            <Tab value="add">Add cards</Tab>
          </TabList>
        </Tabs>
        <Tabs v-if="selectedInventoryItem" v-model:value="activeTab" class="inspector-tabs">
          <TabList>
            <Tab value="card">Card info</Tab>
            <Tab value="edit">Edit card</Tab>
            <Tab value="allocations">Allocations</Tab>
          </TabList>
        </Tabs>
      </div>

      <p v-if="error && activeTab !== 'edit'" class="panel-error" role="alert">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <span>{{ error }}</span>
      </p>

      <section v-if="activeTab === 'info'" class="inspector-content">
        <label class="field"><span>Name</span><InputText v-model="collectionName" /></label>
        <label class="field">
          <span>Owner</span>
          <Select v-model="collectionPlayerId" :options="players" option-label="name" option-value="id" />
        </label>
        <label class="field">
          <span>Created at</span>
          <DatePicker
            v-model="collectionCreatedAt"
            date-format="yy-mm-dd"
            hour-format="24"
            show-icon
            show-time
          />
        </label>
        <label class="toggle-field">
          <ToggleSwitch
            v-model="collectionIsDefault"
            :disabled="selectedCollection?.is_default"
            title="Choose another collection to move the primary marker"
          />
          <span>Primary collection</span>
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="collectionIsWishlist" />
          <span>Wishlist</span>
        </label>
        <label class="field"><span>Note</span><Textarea v-model="collectionNote" rows="4" /></label>
        <details v-if="collectionDirty" class="unsaved-changes">
          <summary>Unsaved changes <span>Show details</span></summary>
          <div v-for="[label, saved, changed] in collectionChanges" :key="label" class="change-row">
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
            :disabled="!collectionCanSave"
            :loading="collectionSaving"
            @click="saveCollectionChanges"
          />
          <Button
            label="Discard changes"
            severity="secondary"
            :disabled="!collectionDirty"
            @click="resetCollectionDraft"
          />
        </div>
      </section>

      <section v-else-if="activeTab === 'card'" class="inspector-content card-info-inspector">
        <template v-if="selectedInventoryItem">
          <p v-if="loadingCardInfo" class="empty-state">Loading card info...</p>
          <template v-else-if="cardInfoDetails">
            <div class="selected-alias">{{ cardInfoName }} ({{ selectedInventoryItem.language }})</div>
            <button
              type="button"
              class="card-image-button"
              aria-label="View selected card image at native resolution"
              :disabled="!cardInfoImageNativeUrl"
              @click="openImageDialog(cardInfoImageNativeUrl)"
            >
              <img
                v-if="cardInfoImageNormalUrl"
                :src="cardInfoImageNormalUrl"
                :alt="cardInfoName"
                :class="{ 'loading-image': cardInfoImageLoading }"
                @load="cardInfoImageLoading = false"
                @error="cardInfoImageLoading = false"
              />
              <span v-if="cardInfoImageLoading" class="card-image-loading-overlay">
                <ProgressSpinner />
              </span>
              <span v-else-if="!cardInfoImageNormalUrl">Image unavailable</span>
            </button>
            <div v-if="cardInfoFaces.length > 1" class="number-toggle-group card-face-toggle">
              <button
                v-for="(face, faceOrder) in cardInfoFaces"
                :key="`${faceOrder}-${face.name}`"
                type="button"
                :class="{ selected: cardInfoFaceOrder === faceOrder }"
                @click="cardInfoFaceOrder = faceOrder"
              >
                {{ face.printed_name ?? face.name ?? `Side ${faceOrder + 1}` }}
              </button>
            </div>
            <div class="card-rules-text">
              <strong>{{ cardInfoType }}</strong>
              <ScryfallSymbolsText v-if="cardInfoManaCost" :text="cardInfoManaCost" />
              <ScryfallSymbolsText v-if="cardInfoText" :text="cardInfoText" />
              <em v-if="cardInfoFlavorText">{{ cardInfoFlavorText }}</em>
            </div>
            <div class="card-info-grid">
              <div>
                <span>Set</span>
                <strong>{{ cardInfoDetails.card.set_name ?? selectedInventoryItem.set_code }}</strong>
              </div>
              <div><span>Collector number</span><strong>#{{ selectedInventoryItem.collector_number }}</strong></div>
              <div><span>Rarity</span><strong>{{ selectedInventoryItem.rarity }}</strong></div>
              <div><span>Language</span><strong>{{ selectedInventoryItem.language }}</strong></div>
              <div v-if="cardInfoDetails.card.cmc != null"><span>Mana value</span><strong>{{ cardInfoDetails.card.cmc }}</strong></div>
              <div v-if="cardInfoStats"><span>{{ cardInfoStats.label }}</span><strong>{{ cardInfoStats.value }}</strong></div>
              <div v-if="cardInfoFace?.artist ?? cardInfoDetails.card.artist"><span>Artist</span><strong>{{ cardInfoFace?.artist ?? cardInfoDetails.card.artist }}</strong></div>
              <div v-if="cardInfoDetails.card.released_at"><span>Released</span><strong>{{ cardInfoDetails.card.released_at }}</strong></div>
              <div><span>Finish</span><strong>{{ selectedInventoryItem.finish }}</strong></div>
              <div><span>Condition</span><strong>{{ selectedInventoryItem.condition_code }}</strong></div>
            </div>
            <div v-if="cardInfoLegalities.length" class="field">
              <span>Legalities</span>
              <div class="legality-list">
                <span
                  v-for="entry in cardInfoLegalities"
                  :key="entry.format"
                  :class="['legality-badge', `legality-${entry.legality}`]"
                >
                  {{ entry.format }}
                </span>
              </div>
            </div>
          </template>
        </template>
      </section>

      <section v-else-if="activeTab === 'edit'" class="inspector-content edit-card-inspector">
        <template v-if="editItem">
          <button
            type="button"
            class="card-image-button"
            aria-label="View edited card image at native resolution"
            :disabled="!editImageNativeUrl"
            @click="openImageDialog(editImageNativeUrl)"
          >
            <img
              v-if="editImageNormalUrl"
              :src="editImageNormalUrl"
              :alt="editItem.name"
              :class="{ 'loading-image': editImageLoading }"
              @load="editImageLoading = false"
              @error="editImageLoading = false"
            />
            <span v-if="editImageLoading" class="card-image-loading-overlay">
              <ProgressSpinner />
            </span>
            <span v-else-if="!editImageNormalUrl">
              {{ loadingEditDetails ? 'Loading image…' : 'Image unavailable' }}
            </span>
          </button>
          <p v-if="editItemAllocated" class="panel-note">
            Attribute changes can be applied to selected copies while preserving deck allocations.
          </p>
          <CardPrintingSelectors
            :printings="editPrintings"
            :preferred-language-code="editItem.language_code"
            :initial-printing-id="editItem.printing_id"
            :initial-language-code="editItem.language_code"
            :initial-finish-id="editItem.finish_id"
            @selection-change="editSelection = $event"
          />
          <div class="compact-field-row">
            <label class="field">
              <span>Condition</span>
              <Select v-model="editCondition" :options="conditions" />
            </label>
            <label class="field">
              <span>Quantity</span>
              <InputNumber v-model="editQuantity" :min="1" show-buttons />
            </label>
          </div>
          <details v-if="editDirty" class="unsaved-changes">
            <summary>Unsaved changes <span>Show details</span></summary>
            <div v-for="[label, saved, changed] in editChanges" :key="label" class="change-row">
              <strong>{{ label }}</strong>
              <span>{{ saved }}</span>
              <i class="pi pi-arrow-right" />
              <span>{{ changed }}</span>
            </div>
          </details>
          <p v-if="editActionError" class="panel-error" role="alert">
            <i class="pi pi-exclamation-triangle" aria-hidden="true" />
            <span>{{ editActionError }}</span>
          </p>
          <div class="panel-actions edit-actions">
            <span v-if="message" class="success-text">{{ message }}</span>
            <Button
              icon="pi pi-save"
              label="Save changes"
              :disabled="!editDirty"
              :loading="saving"
              @click="saveCardChanges"
            />
            <Button
              label="Discard changes"
              severity="secondary"
              :disabled="!editDirty"
              @click="discardEditChanges"
            />
            <Button
              icon="pi pi-trash"
              label="Delete card"
              severity="danger"
              :loading="saving"
              @click="deleteCard"
            />
          </div>
        </template>
      </section>

      <section v-else-if="activeTab === 'allocations'" class="inspector-content allocations-inspector">
        <template v-if="selectedInventoryItem">
          <div class="selected-alias">{{ selectedInventoryItem.name }}</div>
          <div class="allocation-summary-grid">
            <div>
              <span>Owned</span>
              <strong>{{ selectedOwnedQuantity }}</strong>
            </div>
            <div>
              <span>Available</span>
              <strong>{{ selectedAvailableQuantity }}</strong>
            </div>
            <div>
              <span>Allocated</span>
              <strong>{{ selectedAllocatedQuantity }}</strong>
            </div>
          </div>
          <p v-if="!selectedAllocationRows.length" class="empty-state">No deck allocations.</p>
          <div v-else class="allocation-list">
            <div v-for="allocation in selectedAllocationRows" :key="allocation.deck_item_id" class="allocation-row">
              <strong>{{ allocation.deck_name }}</strong>
              <span>{{ allocationSectionLabel(allocation.section) }}</span>
              <b>{{ allocation.quantity }}</b>
            </div>
          </div>
        </template>
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
                  aria-label="Clear card search"
                  @click="clearCardSearch"
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

        <template v-if="selectedAlias && printings.length">
          <div class="card-config-layout">
            <div class="card-image-wrap">
              <div class="selected-alias">{{ cardName }}</div>
              <ScryfallSymbolsText v-if="cardManaCost" class="selected-card-cost" :text="cardManaCost" />
              <button type="button" class="card-image-button" aria-label="View card image at native resolution" :disabled="!imageNativeUrl" @click="openImageDialog(imageNativeUrl)">
                <img
                  v-if="imageNormalUrl"
                  :src="imageNormalUrl"
                  :alt="cardName"
                  :class="{ 'loading-image': previewImageLoading }"
                  @load="previewImageLoading = false"
                  @error="previewImageLoading = false"
                />
                <span v-if="previewImageLoading" class="card-image-loading-overlay">
                  <ProgressSpinner />
                </span>
                <span v-else-if="!imageNormalUrl">{{ loadingDetails ? 'Loading image…' : 'Image unavailable' }}</span>
              </button>
              <div class="card-rules-text">
                <strong>{{ cardType }}</strong>
                <ScryfallSymbolsText :text="cardText" />
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
              <CardPrintingSelectors
                :printings="printings"
                :preferred-language-code="preferredLanguageCode"
                @selection-change="addSelection = $event"
              />
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
      <img v-if="dialogImageUrl" :src="dialogImageUrl" alt="Selected card at native resolution" />
    </dialog>

    <Dialog v-model:visible="createCollectionDialogVisible" modal header="Create collection">
      <div class="dialog-fields">
        <label class="field"><span>Name</span><InputText v-model="newCollectionName" autofocus /></label>
        <label class="field">
          <span>Owner</span>
          <Select v-model="newCollectionPlayerId" :options="players" option-label="name" option-value="id" />
        </label>
        <label class="toggle-field">
          <ToggleSwitch v-model="newCollectionIsWishlist" />
          <span>Wishlist</span>
        </label>
        <p v-if="createCollectionError" class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>{{ createCollectionError }}</span>
        </p>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="createCollectionDialogVisible = false" />
          <Button
            icon="pi pi-plus"
            label="Create collection"
            :disabled="!newCollectionName.trim() || newCollectionPlayerId === null"
            :loading="collectionSaving"
            @click="createCollection"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:visible="attributeUpdateDialogVisible"
      modal
      header="Apply card detail changes"
      class="allocation-resolution-dialog"
    >
      <template v-if="editItem">
        <div class="dialog-fields">
          <p class="panel-note">
            Choose which copies should receive the new card details. Deck allocations will be preserved.
          </p>
          <div class="allocation-resolution-list">
            <div class="allocation-resolution-row">
              <div>
                <strong>Available cards</strong>
                <span>Not allocated to decks</span>
              </div>
              <InputNumber
                :model-value="attributeUpdateAvailableQuantity"
                :min="0"
                :max="attributeUpdateAvailableMax()"
                show-buttons
                @update:model-value="setAttributeUpdateAvailableQuantity($event)"
              />
              <b>/ {{ editItem.available_quantity }}</b>
            </div>
            <div
              v-for="allocation in editItem.allocations"
              :key="allocation.deck_item_id"
              class="allocation-resolution-row"
            >
              <div>
                <strong>{{ allocation.deck_name }}</strong>
                <span>{{ allocationSectionLabel(allocation.section) }}</span>
              </div>
              <InputNumber
                :model-value="attributeUpdateAllocatedQuantity(allocation.deck_item_id)"
                :min="0"
                :max="attributeUpdateAllocationMax(allocation.deck_item_id, allocation.quantity)"
                show-buttons
                @update:model-value="setAttributeUpdateAllocatedQuantity(allocation.deck_item_id, $event)"
              />
              <b>/ {{ allocation.quantity }}</b>
            </div>
          </div>
          <div class="allocation-removal-changes unsaved-changes">
            <div
              v-for="[label, detailsLabel, saved, changed] in attributeUpdateChanges"
              :key="label"
              class="attribute-change-row"
            >
              <strong>{{ label }}</strong>
              <span>{{ detailsLabel }}</span>
              <span>{{ saved }}</span>
              <i class="pi pi-arrow-right" />
              <span>{{ changed }}</span>
            </div>
          </div>
          <p class="allocation-progress" :class="{ valid: attributeUpdateValid, invalid: !attributeUpdateValid }">
            {{
              attributeUpdateValid
                ? `Selected ${selectedAttributeUpdateQuantity} ${selectedAttributeUpdateQuantity === 1 ? 'copy' : 'copies'} to update.`
                : 'Select at least 1 copy to update.'
            }}
          </p>
        </div>
      </template>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="attributeUpdateDialogVisible = false" />
          <Button
            icon="pi pi-save"
            label="Save changes"
            :disabled="!attributeUpdateValid"
            :loading="saving"
            @click="confirmAttributeUpdate"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:visible="allocationRemovalDialogVisible"
      modal
      header="Choose affected deck copies"
      class="allocation-resolution-dialog"
    >
      <template v-if="editItem">
        <div class="dialog-fields">
          <p class="panel-note">
            Select exactly {{ requiredAllocationRemovals }} deck-allocated
            {{ requiredAllocationRemovals === 1 ? 'copy' : 'copies' }} to remove.
            {{ requiredAllocationRemovals === 1 ? 'This copy' : 'These copies' }}
            will also be removed from this collection.
          </p>
          <div class="allocation-resolution-list">
            <div
              v-for="allocation in editItem.allocations"
              :key="allocation.deck_item_id"
              class="allocation-resolution-row"
            >
              <div>
                <strong>{{ allocation.deck_name }}</strong>
                <span>{{ allocationSectionLabel(allocation.section) }}</span>
              </div>
              <InputNumber
                :model-value="allocationRemovalQuantity(allocation.deck_item_id)"
                :min="0"
                :max="allocationRemovalMax(allocation.deck_item_id, allocation.quantity)"
                show-buttons
                @update:model-value="setAllocationRemovalQuantity(allocation.deck_item_id, $event)"
              />
              <b>/ {{ allocation.quantity }}</b>
            </div>
          </div>
          <div class="allocation-removal-changes unsaved-changes">
            <div v-for="[label, saved, changed] in allocationRemovalChanges" :key="label" class="change-row">
              <strong>{{ label }}</strong>
              <span>{{ saved }}</span>
              <i class="pi pi-arrow-right" />
              <span>{{ changed }}</span>
            </div>
          </div>
          <p class="allocation-progress" :class="{ valid: allocationRemovalValid, invalid: !allocationRemovalValid }">
            Selected {{ selectedAllocationRemovals }} of {{ requiredAllocationRemovals }} required allocated copies.
          </p>
        </div>
      </template>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="allocationRemovalDialogVisible = false" />
          <Button
            icon="pi pi-save"
            label="Save changes"
            :disabled="!allocationRemovalValid"
            :loading="saving"
            @click="confirmAllocationRemovalSave"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:visible="deleteAllocatedCardDialogVisible"
      modal
      header="Delete allocated card"
      class="allocation-resolution-dialog"
    >
      <template v-if="editItem">
        <div class="dialog-fields">
          <p class="panel-error" role="alert">
            <i class="pi pi-exclamation-triangle" aria-hidden="true" />
            <span>
              This card is allocated to decks. Deleting it from the collection will also remove these deck allocations.
            </span>
          </p>
          <div class="allocation-list">
            <div v-for="allocation in editItem.allocations" :key="allocation.deck_item_id" class="allocation-row">
              <strong>{{ allocation.deck_name }}</strong>
              <span>{{ allocationSectionLabel(allocation.section) }}</span>
              <b>{{ allocation.quantity }}</b>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="deleteAllocatedCardDialogVisible = false" />
          <Button
            icon="pi pi-trash"
            label="Delete card"
            severity="danger"
            :loading="saving"
            @click="confirmDeleteAllocatedCard"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model:visible="deleteAllocatedCollectionDialogVisible"
      modal
      header="Delete allocated collection"
      class="allocation-resolution-dialog"
    >
      <div class="dialog-fields">
        <p class="panel-error" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />
          <span>
            This collection contains cards allocated to decks. Deleting the collection will also remove those deck allocations.
          </span>
        </p>
        <div class="collection-allocation-delete-list">
          <div
            v-for="item in deleteCollectionAllocationItems"
            :key="item.collection_item_id"
            class="collection-allocation-delete-item"
          >
            <strong>{{ item.name }}</strong>
            <div class="collection-allocation-deck-list">
              <div
                v-for="group in collectionAllocationDeckGroups(item)"
                :key="group.deckId"
                class="collection-allocation-deck-row"
              >
                <span>{{ group.deckName }}</span>
                <b>
                  <template
                    v-for="(section, sectionIndex) in group.sections"
                    :key="`${group.deckId}-${section.section}`"
                  >
                    <span v-if="sectionIndex > 0">, </span>
                    {{ allocationSectionLabel(section.section) }} x{{ section.quantity }}
                  </template>
                </b>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-actions">
          <Button label="Cancel" severity="secondary" @click="deleteAllocatedCollectionDialogVisible = false" />
          <Button
            icon="pi pi-trash"
            label="Delete collection"
            severity="danger"
            :loading="collectionSaving"
            @click="confirmDeleteAllocatedCollection"
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

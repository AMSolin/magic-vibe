const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export type CatalogImport = {
  id: number;
  source: string;
  source_updated_at: number | null;
  started_at: number;
  finished_at: number | null;
  status: string;
  error_message: string | null;
  catalog_row_count: number | null;
  source_file_size: number | null;
  source_sha256: string | null;
};

export type CatalogStatus = {
  latest_import: CatalogImport | null;
  latest_successful_import: CatalogImport | null;
  latest_source_index_updated_at: number | null;
  installed_source_index_updated_at: number | null;
  source_index_status: 'current' | 'outdated' | 'unknown' | 'not_installed';
  source_index_error: string | null;
};

export type UserDataStatus = {
  exists: boolean;
  file_size: number | null;
  modified_at: number | null;
};

export type ScryfallSymbolsStatus = {
  exists: boolean;
  symbol_count: number;
  updated_at: number | null;
};

export type DelverLensMappingStatus = {
  exists: boolean;
  database_path: string;
  database_file_size: number | null;
  database_modified_at: number | null;
  row_count: number | null;
  unique_scryfall_ids: number | null;
  apk_exists: boolean;
  apk_path: string;
  apk_file_size: number | null;
  apk_modified_at: number | null;
  source_url: string | null;
  apk_url: string | null;
  source_app_version: string | null;
  source_release_date: number | null;
  latest_source_app_version: string | null;
  latest_source_release_date: number | null;
  source_status: 'current' | 'outdated' | 'unknown' | 'not_installed';
  source_status_error: string | null;
  source_db_member: string | null;
  source_table: string | null;
  updated_at: number | null;
  last_error: string | null;
};

export type GeneratedTestCollection = {
  id: number;
  name: string;
  language_code: string;
  rows: number;
  unique_scryfall_ids: number;
  total_quantity: number;
};

export type GeneratedTestCollections = {
  collections: GeneratedTestCollection[];
};

export type ScryfallSymbol = {
  image_url: string;
  label: string;
};

export type ScryfallSymbols = Record<string, ScryfallSymbol>;

export type WorkspaceCollection = {
  id: number;
  player_id: number | null;
  name: string;
  is_default: boolean;
  is_wishlist: boolean;
  note: string | null;
  created_at: number;
};

export type WorkspaceCollectionAllocationSummary = {
  collection_item_id: number;
  name: string;
  allocations: WorkspaceDeckInventoryAllocation[];
};

export type WorkspaceCollectionAllocationDeleteDetail = {
  message: string;
  allocation_signature: string;
  items: WorkspaceCollectionAllocationSummary[];
};

export type WorkspacePlayer = {
  id: number;
  name: string;
  is_default: boolean;
  created_at: number;
};

export type WorkspaceDeck = {
  id: number;
  player_id: number | null;
  name: string;
  is_wish: boolean;
  note: string | null;
  created_at: number;
  updated_at: number;
};

export type WorkspaceDeckWrite = {
  name: string;
  player_id: number;
  note: string | null;
  is_wish?: boolean;
  created_at?: number;
};

export type WorkspaceDeckItem = {
  id: number;
  collection_item_id: number | null;
  printing_id: number | null;
  release_date: number | null;
  language_code: string | null;
  collection_id: number | null;
  collection_name: string | null;
  set_code: string | null;
  keyrune_code: string | null;
  collector_number: string | null;
  language: string | null;
  finish_id: number | null;
  finish: string | null;
  condition_code: string | null;
  owned_quantity: number | null;
  allocated_quantity: number | null;
  available_quantity: number | null;
  section: string;
  quantity: number;
  name: string;
  oracle_id: string;
};

export type WorkspaceWishDeckSearchResult = {
  oracle_id: string;
  language_code: string;
  language: string;
  name: string;
  type: string;
  mana_cost: string;
  printing_id: number | null;
  release_date: number | null;
};

export type WorkspaceWishDeckItem = WorkspaceWishDeckSearchResult & {
  id: number;
  section: string;
  quantity: number;
  linked_collection_item_id: number | null;
};

export type WorkspaceDeckInventoryAllocation = {
  deck_item_id: number;
  deck_id: number;
  deck_name: string;
  section: string;
  quantity: number;
};

export type WorkspaceDeckInventoryItem = {
  collection_item_id: number;
  collection_id: number;
  collection_name: string;
  printing_id: number;
  release_date: number;
  name: string;
  set_code: string;
  keyrune_code: string;
  collector_number: string;
  language_code: string;
  language: string;
  finish_id: number;
  finish: string;
  condition_code: string;
  owned_quantity: number;
  allocated_quantity: number;
  available_quantity: number;
  allocations: WorkspaceDeckInventoryAllocation[];
};

export type WorkspaceDeckInventorySearchResult = {
  oracle_id: string;
  name: string;
  language_code: string;
  total_owned: number;
  total_available: number;
  items: WorkspaceDeckInventoryItem[];
};

export type WorkspaceDeckInventorySearchPage = {
  results: WorkspaceDeckInventorySearchResult[];
  total_count: number;
  total_items: number;
};

export type WorkspaceDeckInventorySearchFilters = {
  search_field: 'name' | 'type' | 'text';
  colors: string[];
  rarities: string[];
  mana_value_min: number | null;
  mana_value_max: number | null;
  color_match: 'includes_all' | 'includes_any' | 'exactly';
  has_uncolored_mana: boolean;
  has_colorless_mana: boolean;
  has_generic_mana: boolean;
  no_colors: boolean;
};

export type WorkspacePlayerWrite = {
  name: string;
  is_default: boolean;
  created_at?: number;
};

export type WorkspaceCollectionWrite = {
  name: string;
  player_id: number;
  note: string | null;
  is_default: boolean;
  is_wishlist: boolean;
  created_at?: number;
};

export type ImportTargetType = 'collection' | 'wishlist' | 'deck' | 'wishdeck';
export type ImportTargetCollectionMode = 'new' | 'existing' | 'import';
export type ImportMergeSection = 'keep' | 'main' | 'side' | 'maybe' | 'commander';

export type DelverLensImportAttributeChange = {
  source_card_id: number;
  source_list_id: number;
  container_name: string;
  card_name: string;
  quantity: number;
  target_type?: ImportTargetType;
  attribute: 'language' | 'finish';
  before_code: string | number;
  before: string;
  after_code: string | number;
  after: string;
  reason: string;
};

export type DelverLensImportCard = {
  id?: number;
  source_card_id: number;
  source_list_id: number;
  delver_card_id: number;
  printing_id: number | null;
  scryfall_id: string | null;
  oracle_id: string | null;
  name: string;
  set_code: string | null;
  collector_number: string | null;
  mana_cost: string;
  type: string;
  quantity: number;
  section: string;
  condition_code: string | null;
  language_code: string | null;
  language: string | null;
  finish_id: number | null;
  finish: string | null;
  attribute_changes: DelverLensImportAttributeChange[];
  warnings: string[];
  errors: string[];
};

export type DelverLensImportEntity = {
  id: number;
  source_list_id: number;
  source_category: number;
  source_category_label: string;
  target_type: ImportTargetType;
  target_type_label: string;
  name: string;
  note: string | null;
  player_id: number;
  created_at: number;
  source_background: number | null;
  source_tab: number | null;
  source_uuid: string | null;
  target_collection_mode: ImportTargetCollectionMode | null;
  target_collection_id: number | null;
  target_import_list_id: number | null;
  card_count: number;
  total_quantity: number;
  mapped_count: number;
  error_count: number;
  warning_count: number;
  errors: string[];
  warnings: string[];
  attribute_changes: DelverLensImportAttributeChange[];
  cards: DelverLensImportCard[];
};

export type DelverLensImportPreview = {
  session_id: string;
  status: 'draft' | 'completed';
  source_filename: string;
  source: {
    kind: 'delver-lens-dlens';
    version: string | null;
    timestamp: string | null;
  };
  default_player_id: number;
  selected_entity_id: number | null;
  entities: DelverLensImportEntity[];
};

export type DelverLensImportEntityEdit = {
  id: number;
  source_list_id: number;
  target_type: ImportTargetType;
  name: string;
  note: string | null;
  player_id: number;
  created_at: number;
  target_collection_mode: ImportTargetCollectionMode | null;
  target_collection_id: number | null;
  target_import_list_id: number | null;
};

export type DelverLensImportResult = {
  created_collections: WorkspaceCollection[];
  updated_collections: WorkspaceCollection[];
  created_decks: WorkspaceDeck[];
  attribute_changes: DelverLensImportAttributeChange[];
};

export type CardSuggestion = {
  oracle_id: string;
  face_order: number;
  language_code: string;
  language: string;
  name: string;
};

export type PrintingFinish = {
  id: number;
  name: string;
};

export type PrintingLocalization = {
  code: string;
  name: string;
};

export type CardPrinting = {
  id: number;
  scryfall_id: string;
  set_code: string;
  set_name: string;
  keyrune_code: string;
  release_date: number;
  collector_number: string;
  language_code: string;
  language: string;
  rarity: string;
  finishes: PrintingFinish[];
  localizations: PrintingLocalization[];
};

export type PrintingOptions = {
  oracle_id: string;
  preferred_language_code: string;
  printings: CardPrinting[];
};

export type ScryfallCard = {
  name?: string;
  printed_name?: string;
  mana_cost?: string;
  cmc?: number;
  type_line?: string;
  printed_type_line?: string;
  oracle_text?: string;
  printed_text?: string;
  flavor_text?: string;
  power?: string;
  toughness?: string;
  loyalty?: string;
  defense?: string;
  artist?: string;
  set_name?: string;
  released_at?: string;
  collector_number?: string;
  rarity?: string;
  legalities?: Record<string, string>;
  card_faces?: ScryfallCardFace[];
};

export type ScryfallCardFace = {
  name?: string;
  printed_name?: string;
  mana_cost?: string;
  type_line?: string;
  printed_type_line?: string;
  oracle_text?: string;
  printed_text?: string;
  flavor_text?: string;
  power?: string;
  toughness?: string;
  loyalty?: string;
  defense?: string;
  artist?: string;
};

export type CardDetails = {
  printing_id: number;
  image_normal_url: string | null;
  image_native_url: string | null;
  card: ScryfallCard;
};

export type WorkspaceCollectionItem = {
  id: number;
  printing_id: number;
  collection_id: number;
  scryfall_id: string;
  oracle_id: string;
  name: string;
  set_code: string;
  keyrune_code: string;
  rarity: string;
  collector_number: string;
  language_code: string;
  language: string;
  finish_id: number;
  finish: string;
  condition_code: string;
  quantity: number;
  allocated_quantity: number;
  available_quantity: number;
  allocations: WorkspaceDeckInventoryAllocation[];
  mana_cost: string;
  type: string;
};

type ApiErrorBody = {
  detail?: unknown;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function formatApiErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'object' && item !== null && 'msg' in item) {
          return String(item.msg);
        }
        return null;
      })
      .filter((message): message is string => message !== null);

    return messages.length > 0 ? messages.join('; ') : null;
  }

  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    return String(detail.message);
  }

  return null;
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    let detail: string | null = null;
    let rawDetail: unknown;
    try {
      const body = (await response.json()) as ApiErrorBody;
      rawDetail = body.detail;
      detail = formatApiErrorDetail(body.detail);
    } catch {
      // Fall back to the HTTP status when the response body is not JSON.
    }

    throw new ApiError(detail ?? `API request failed: ${response.status}`, response.status, rawDetail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function requestResponse(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    let detail: string | null = null;
    let rawDetail: unknown;
    try {
      const body = (await response.json()) as ApiErrorBody;
      rawDetail = body.detail;
      detail = formatApiErrorDetail(body.detail);
    } catch {
      // Fall back to the HTTP status when the response body is not JSON.
    }

    throw new ApiError(detail ?? `API request failed: ${response.status}`, response.status, rawDetail);
  }

  return response;
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail: string | null = null;
    let rawDetail: unknown;
    try {
      const body = (await response.json()) as ApiErrorBody;
      rawDetail = body.detail;
      detail = formatApiErrorDetail(body.detail);
    } catch {
      // Fall back to the HTTP status when the response body is not JSON.
    }

    throw new ApiError(detail ?? `API request failed: ${response.status}`, response.status, rawDetail);
  }

  return response.json() as Promise<T>;
}

export function getCatalogStatus(): Promise<CatalogStatus> {
  return request<CatalogStatus>('/api/admin/catalog');
}

export function startCatalogUpdate(): Promise<CatalogImport> {
  return request<CatalogImport>('/api/admin/catalog/update', {
    method: 'POST',
  });
}

export function startCatalogRebuild(): Promise<CatalogImport> {
  return request<CatalogImport>('/api/admin/catalog/rebuild', {
    method: 'POST',
  });
}

export function getUserDataStatus(): Promise<UserDataStatus> {
  return request<UserDataStatus>('/api/admin/user-data');
}

export function recreateUserData(): Promise<UserDataStatus> {
  return request<UserDataStatus>('/api/admin/user-data/recreate', {
    method: 'POST',
  });
}

export function getScryfallSymbolsStatus(): Promise<ScryfallSymbolsStatus> {
  return request<ScryfallSymbolsStatus>('/api/admin/scryfall-symbols');
}

export function updateScryfallSymbols(): Promise<ScryfallSymbolsStatus> {
  return request<ScryfallSymbolsStatus>('/api/admin/scryfall-symbols/update', {
    method: 'POST',
  });
}

export function getDelverLensMappingStatus(): Promise<DelverLensMappingStatus> {
  return request<DelverLensMappingStatus>('/api/admin/delver-lens-mapping');
}

export function updateDelverLensMapping(forceDownload = false): Promise<DelverLensMappingStatus> {
  const params = new URLSearchParams({ force_download: String(forceDownload) });
  return request<DelverLensMappingStatus>(`/api/admin/delver-lens-mapping/update?${params.toString()}`, {
    method: 'POST',
  });
}

export function generateAdminTestCollections(): Promise<GeneratedTestCollections> {
  return request<GeneratedTestCollections>('/api/admin/test-collections/generate', {
    method: 'POST',
  });
}

export function previewDelverLensImport(file: File): Promise<DelverLensImportPreview> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm<DelverLensImportPreview>('/api/import/delver-lens/preview', formData);
}

export function getDelverLensImportSession(sessionId: string): Promise<DelverLensImportPreview> {
  return request<DelverLensImportPreview>(`/api/import/delver-lens/sessions/${sessionId}`);
}

export function clearDelverLensImportSession(sessionId: string): Promise<void> {
  return request<void>(`/api/import/delver-lens/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

export function updateDelverLensImportEntity(
  sessionId: string,
  entityId: number,
  entity: DelverLensImportEntityEdit,
): Promise<DelverLensImportPreview> {
  return request<DelverLensImportPreview>(`/api/import/delver-lens/sessions/${sessionId}/entities/${entityId}`, {
    method: 'PATCH',
    body: JSON.stringify(entity),
  });
}

export function deleteDelverLensImportEntity(
  sessionId: string,
  entityId: number,
): Promise<DelverLensImportPreview> {
  return request<DelverLensImportPreview>(`/api/import/delver-lens/sessions/${sessionId}/entities/${entityId}`, {
    method: 'DELETE',
  });
}

export function mergeDelverLensImportEntity(
  sessionId: string,
  entityId: number,
  targetEntityId: number,
  mergeSection: ImportMergeSection,
): Promise<DelverLensImportPreview> {
  return request<DelverLensImportPreview>(
    `/api/import/delver-lens/sessions/${sessionId}/entities/${entityId}/merge`,
    {
      method: 'POST',
      body: JSON.stringify({ target_entity_id: targetEntityId, merge_section: mergeSection }),
    },
  );
}

export function applyDelverLensImport(sessionId: string): Promise<DelverLensImportResult> {
  return request<DelverLensImportResult>(`/api/import/delver-lens/sessions/${sessionId}/apply`, {
    method: 'POST',
  });
}

export function listWorkspaceSymbols(): Promise<ScryfallSymbols> {
  return request<ScryfallSymbols>('/api/workspace/symbols');
}

export function listWorkspaceCollections(): Promise<WorkspaceCollection[]> {
  return request<WorkspaceCollection[]>('/api/workspace/collections');
}

export function listWorkspacePlayers(): Promise<WorkspacePlayer[]> {
  return request<WorkspacePlayer[]>('/api/workspace/players');
}

export function listWorkspaceDecks(): Promise<WorkspaceDeck[]> {
  return request<WorkspaceDeck[]>('/api/workspace/decks');
}

export function createWorkspaceDeck(payload: WorkspaceDeckWrite): Promise<WorkspaceDeck> {
  return request<WorkspaceDeck>('/api/workspace/decks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceDeck(
  deckId: number,
  payload: Omit<WorkspaceDeckWrite, 'is_wish'>,
): Promise<WorkspaceDeck> {
  return request<WorkspaceDeck>(`/api/workspace/decks/${deckId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspaceDeck(deckId: number): Promise<void> {
  return request<void>(`/api/workspace/decks/${deckId}`, {
    method: 'DELETE',
  });
}

export function listWorkspaceDeckItems(deckId: number): Promise<WorkspaceDeckItem[]> {
  return request<WorkspaceDeckItem[]>(`/api/workspace/decks/${deckId}/items`);
}

export function searchWorkspaceDeckInventory(
  deckId: number,
  query: string,
  oracleId?: string,
  filters?: WorkspaceDeckInventorySearchFilters,
  page?: { offset: number; limit: number },
): Promise<WorkspaceDeckInventorySearchPage> {
  const params = new URLSearchParams({ query });
  if (page) {
    params.set('offset', String(page.offset));
    params.set('limit', String(page.limit));
  }
  if (oracleId) {
    params.set('oracle_id', oracleId);
  }
  if (filters) {
    params.set('search_field', filters.search_field);
    for (const color of filters.colors) {
      params.append('colors', color);
    }
    for (const rarity of filters.rarities) {
      params.append('rarities', rarity);
    }
    if (filters.mana_value_min !== null) {
      params.set('mana_value_min', String(filters.mana_value_min));
    }
    if (filters.mana_value_max !== null) {
      params.set('mana_value_max', String(filters.mana_value_max));
    }
    params.set('color_match', filters.color_match);
    if (filters.has_uncolored_mana) {
      params.set('has_uncolored_mana', 'true');
    }
    if (filters.has_colorless_mana) {
      params.set('has_colorless_mana', 'true');
    }
    if (filters.has_generic_mana) {
      params.set('has_generic_mana', 'true');
    }
    if (filters.no_colors) {
      params.set('no_colors', 'true');
    }
  }
  return requestResponse(`/api/workspace/decks/${deckId}/items/search?${params.toString()}`).then(
    async (response) => {
      const results = (await response.json()) as WorkspaceDeckInventorySearchResult[];
      return {
        results,
        total_count: Number(response.headers.get('X-Total-Count') ?? results.length),
        total_items: Number(
          response.headers.get('X-Total-Items') ??
            results.reduce((sum, result) => sum + result.items.length, 0),
        ),
      };
    },
  );
}

export function addWorkspaceDeckItem(
  deckId: number,
  payload: {
    collection_item_id: number;
    section: string;
    quantity?: number;
  },
): Promise<WorkspaceDeckItem> {
  return request<WorkspaceDeckItem>(`/api/workspace/decks/${deckId}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceDeckItem(
  deckId: number,
  itemId: number,
  payload: {
    section?: string;
    quantity?: number;
  },
): Promise<WorkspaceDeckItem> {
  return request<WorkspaceDeckItem>(`/api/workspace/decks/${deckId}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspaceDeckItem(deckId: number, itemId: number): Promise<void> {
  return request<void>(`/api/workspace/decks/${deckId}/items/${itemId}`, {
    method: 'DELETE',
  });
}

export function listWorkspaceWishDeckItems(deckId: number): Promise<WorkspaceWishDeckItem[]> {
  return request<WorkspaceWishDeckItem[]>(`/api/workspace/decks/${deckId}/wish-items`);
}

export function searchWorkspaceWishDeckCards(
  deckId: number,
  query: string,
  filters: WorkspaceDeckInventorySearchFilters,
  page?: { offset: number; limit: number },
): Promise<{
  results: WorkspaceWishDeckSearchResult[];
  total_count: number;
  total_items: number;
}> {
  const params = new URLSearchParams({ query, search_field: filters.search_field });
  filters.colors.forEach((color) => params.append('colors', color));
  filters.rarities.forEach((rarity) => params.append('rarities', rarity));
  params.set('color_match', filters.color_match);
  if (filters.mana_value_min !== null) {
    params.set('mana_value_min', String(filters.mana_value_min));
  }
  if (filters.mana_value_max !== null) {
    params.set('mana_value_max', String(filters.mana_value_max));
  }
  if (filters.has_uncolored_mana) {
    params.set('has_uncolored_mana', 'true');
  }
  if (filters.has_colorless_mana) {
    params.set('has_colorless_mana', 'true');
  }
  if (filters.has_generic_mana) {
    params.set('has_generic_mana', 'true');
  }
  if (filters.no_colors) {
    params.set('no_colors', 'true');
  }
  if (page) {
    params.set('offset', String(page.offset));
    params.set('limit', String(page.limit));
  }
  return requestResponse(`/api/workspace/decks/${deckId}/wish-items/search?${params.toString()}`).then(
    async (response) => {
      const results = (await response.json()) as WorkspaceWishDeckSearchResult[];
      return {
        results,
        total_count: Number(response.headers.get('X-Total-Count') ?? results.length),
        total_items: Number(response.headers.get('X-Total-Items') ?? results.length),
      };
    },
  );
}

export function addWorkspaceWishDeckItem(
  deckId: number,
  payload: {
    oracle_id: string;
    language_code: string;
    section: string;
    quantity?: number;
  },
): Promise<WorkspaceWishDeckItem> {
  return request<WorkspaceWishDeckItem>(`/api/workspace/decks/${deckId}/wish-items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceWishDeckItem(
  deckId: number,
  itemId: number,
  payload: {
    section?: string;
    quantity?: number;
  },
): Promise<WorkspaceWishDeckItem> {
  return request<WorkspaceWishDeckItem>(`/api/workspace/decks/${deckId}/wish-items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspaceWishDeckItem(deckId: number, itemId: number): Promise<void> {
  return request<void>(`/api/workspace/decks/${deckId}/wish-items/${itemId}`, {
    method: 'DELETE',
  });
}

export function createWorkspacePlayer(payload: WorkspacePlayerWrite): Promise<WorkspacePlayer> {
  return request<WorkspacePlayer>('/api/workspace/players', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspacePlayer(
  playerId: number,
  payload: WorkspacePlayerWrite,
): Promise<WorkspacePlayer> {
  return request<WorkspacePlayer>(`/api/workspace/players/${playerId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspacePlayer(
  playerId: number,
  confirmCollectionOwnerClear = false,
): Promise<void> {
  const params = confirmCollectionOwnerClear
    ? `?${new URLSearchParams({ confirm_collection_owner_clear: 'true' }).toString()}`
    : '';
  return request<void>(`/api/workspace/players/${playerId}${params}`, {
    method: 'DELETE',
  });
}

export function createWorkspaceCollection(
  payload: WorkspaceCollectionWrite,
): Promise<WorkspaceCollection> {
  return request<WorkspaceCollection>('/api/workspace/collections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceCollection(
  collectionId: number,
  payload: WorkspaceCollectionWrite,
): Promise<WorkspaceCollection> {
  return request<WorkspaceCollection>(`/api/workspace/collections/${collectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteWorkspaceCollection(
  collectionId: number,
  options: { remove_allocations?: boolean; allocation_signature?: string } = {},
): Promise<void> {
  const params = new URLSearchParams();
  if (options.remove_allocations) {
    params.set('remove_allocations', 'true');
  }
  if (options.allocation_signature) {
    params.set('allocation_signature', options.allocation_signature);
  }
  const query = params.toString();
  return request<void>(`/api/workspace/collections/${collectionId}${query ? `?${query}` : ''}`, {
    method: 'DELETE',
  });
}

export function suggestWorkspaceCards(query: string, exact: boolean): Promise<CardSuggestion[]> {
  const params = new URLSearchParams({ query, exact: String(exact) });
  return request<CardSuggestion[]>(`/api/workspace/cards/suggest?${params.toString()}`);
}

export function listWorkspacePrintings(
  oracleId: string,
  preferredLanguageCode: string,
): Promise<PrintingOptions> {
  const params = new URLSearchParams({ preferred_language_code: preferredLanguageCode });
  return request<PrintingOptions>(
    `/api/workspace/cards/${oracleId}/printings?${params.toString()}`,
  );
}

export function getWorkspacePrintingDetails(
  printingId: number,
  languageCode?: string,
): Promise<CardDetails> {
  const params = languageCode
    ? `?${new URLSearchParams({ language_code: languageCode }).toString()}`
    : '';
  return request<CardDetails>(`/api/workspace/printings/${printingId}/details${params}`);
}

export function listWorkspaceCollectionItems(
  collectionId: number,
): Promise<WorkspaceCollectionItem[]> {
  return request<WorkspaceCollectionItem[]>(`/api/workspace/collections/${collectionId}/items`);
}

export function addWorkspaceCollectionItem(
  collectionId: number,
  payload: {
    printing_id: number;
    finish_id: number;
    language_code: string;
    condition_code: string;
    quantity: number;
  },
): Promise<WorkspaceCollectionItem> {
  return request<WorkspaceCollectionItem>(`/api/workspace/collections/${collectionId}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceCollectionItem(
  collectionId: number,
  itemId: number,
  payload: {
    printing_id: number;
    finish_id: number;
    language_code: string;
    condition_code: string;
    quantity: number;
    allocation_removals?: { deck_item_id: number; quantity: number }[];
    attribute_update?: {
      available_quantity: number;
      allocation_selections: { deck_item_id: number; quantity: number }[];
      source_quantity: number;
      allocation_signature: string;
    };
  },
): Promise<WorkspaceCollectionItem> {
  return request<WorkspaceCollectionItem>(
    `/api/workspace/collections/${collectionId}/items/${itemId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteWorkspaceCollectionItem(
  collectionId: number,
  itemId: number,
  options: { remove_allocations?: boolean } = {},
): Promise<void> {
  const params = new URLSearchParams();
  if (options.remove_allocations) {
    params.set('remove_allocations', 'true');
  }
  const query = params.toString();
  return request<void>(`/api/workspace/collections/${collectionId}/items/${itemId}${query ? `?${query}` : ''}`, {
    method: 'DELETE',
  });
}

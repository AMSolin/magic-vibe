const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export type Card = {
  id: number;
  card_uuid: string;
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  image_small: string | null;
  image_normal: string | null;
};

export type Collection = {
  id: number;
  name: string;
  owner_id: number;
  note: string | null;
  is_default: boolean;
  is_wishlist: boolean;
  created_at: string;
};

export type CollectionCreate = {
  name: string;
  note?: string | null;
  is_default?: boolean;
  is_wishlist?: boolean;
};

export type CollectionUpdate = {
  name?: string;
  owner_id?: number;
  note?: string | null;
  is_default?: boolean;
  is_wishlist?: boolean;
  created_at?: string;
};

export type CollectionItem = {
  id: number;
  collection_id: number;
  card_uuid: string;
  card: Card;
  quantity: number;
  condition_code: string;
  foil: boolean;
  language: string;
  created_at: string;
  allocated_quantity: number;
  available_quantity: number;
};

export type CollectionItemCreate = {
  card_uuid: string;
  quantity?: number;
  condition_code?: string;
  foil?: boolean;
  language?: string;
};

export type CollectionItemUpdate = {
  quantity?: number;
  condition_code?: string;
  foil?: boolean;
  language?: string;
};

export type CollectionItemMove = {
  collection_id: number;
};

export type Deck = {
  id: number;
  name: string;
  owner_id: number;
  note: string | null;
  is_default: boolean;
  is_wishlist: boolean;
  wishlist_collection_id: number | null;
  created_at: string;
};

export type DeckCreate = {
  name: string;
  owner_id?: number;
  note?: string | null;
  is_default?: boolean;
  is_wishlist?: boolean;
  wishlist_collection_id?: number | null;
};

export type DeckUpdate = {
  name?: string;
  owner_id?: number;
  note?: string | null;
  is_default?: boolean;
  is_wishlist?: boolean;
  wishlist_collection_id?: number | null;
  created_at?: string;
};

export type DeckItem = {
  id: number;
  deck_id: number;
  collection_item_id: number;
  quantity: number;
  section: string;
  is_commander: boolean;
  collection_item: CollectionItem;
};

export type DeckItemCreate = {
  collection_item_id: number;
  quantity?: number;
  section?: string;
  is_commander?: boolean;
};

export type DeckItemUpdate = {
  quantity?: number;
  section?: string;
  is_commander?: boolean;
};

export type DeckItemMove = {
  section: string;
  quantity?: number;
};

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

export type ScryfallSymbol = {
  image_url: string;
  label: string;
};

export type ScryfallSymbols = Record<string, ScryfallSymbol>;

export type WorkspaceCollection = {
  id: number;
  name: string;
  is_default: boolean;
  is_wishlist: boolean;
  note: string | null;
  created_at: number;
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
    try {
      const body = (await response.json()) as ApiErrorBody;
      detail = formatApiErrorDetail(body.detail);
    } catch {
      // Fall back to the HTTP status when the response body is not JSON.
    }

    throw new ApiError(detail ?? `API request failed: ${response.status}`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function searchCards(search: string): Promise<Card[]> {
  const query = new URLSearchParams();
  if (search.trim()) {
    query.set('search', search.trim());
  }

  return request<Card[]>(`/api/cards?${query.toString()}`);
}

export function listCollections(): Promise<Collection[]> {
  return request<Collection[]>('/api/collections');
}

export function createCollection(payload: CollectionCreate): Promise<Collection> {
  return request<Collection>('/api/collections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCollection(
  collectionId: number,
  payload: CollectionUpdate,
): Promise<Collection> {
  return request<Collection>(`/api/collections/${collectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteCollection(collectionId: number): Promise<void> {
  return request<void>(`/api/collections/${collectionId}`, {
    method: 'DELETE',
  });
}

export function listCollectionItems(collectionId: number): Promise<CollectionItem[]> {
  return request<CollectionItem[]>(`/api/collections/${collectionId}/items`);
}

export function addCollectionItem(
  collectionId: number,
  payload: CollectionItemCreate,
): Promise<CollectionItem> {
  return request<CollectionItem>(`/api/collections/${collectionId}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCollectionItem(
  collectionId: number,
  itemId: number,
  payload: CollectionItemUpdate,
): Promise<CollectionItem> {
  return request<CollectionItem>(`/api/collections/${collectionId}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteCollectionItem(collectionId: number, itemId: number): Promise<void> {
  return request<void>(`/api/collections/${collectionId}/items/${itemId}`, {
    method: 'DELETE',
  });
}

export function moveCollectionItem(
  collectionId: number,
  itemId: number,
  payload: CollectionItemMove,
): Promise<CollectionItem> {
  return request<CollectionItem>(`/api/collections/${collectionId}/items/${itemId}/move`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listDecks(): Promise<Deck[]> {
  return request<Deck[]>('/api/decks');
}

export function createDeck(payload: DeckCreate): Promise<Deck> {
  return request<Deck>('/api/decks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateDeck(deckId: number, payload: DeckUpdate): Promise<Deck> {
  return request<Deck>(`/api/decks/${deckId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteDeck(deckId: number): Promise<void> {
  return request<void>(`/api/decks/${deckId}`, {
    method: 'DELETE',
  });
}

export function listDeckItems(deckId: number): Promise<DeckItem[]> {
  return request<DeckItem[]>(`/api/decks/${deckId}/items`);
}

export function addDeckItem(deckId: number, payload: DeckItemCreate): Promise<DeckItem> {
  return request<DeckItem>(`/api/decks/${deckId}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateDeckItem(
  deckId: number,
  itemId: number,
  payload: DeckItemUpdate,
): Promise<DeckItem> {
  return request<DeckItem>(`/api/decks/${deckId}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteDeckItem(deckId: number, itemId: number): Promise<void> {
  return request<void>(`/api/decks/${deckId}/items/${itemId}`, {
    method: 'DELETE',
  });
}

export function moveDeckItem(
  deckId: number,
  itemId: number,
  payload: DeckItemMove,
): Promise<DeckItem> {
  return request<DeckItem>(`/api/decks/${deckId}/items/${itemId}/move`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
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

export function listWorkspaceSymbols(): Promise<ScryfallSymbols> {
  return request<ScryfallSymbols>('/api/workspace/symbols');
}

export function listWorkspaceCollections(): Promise<WorkspaceCollection[]> {
  return request<WorkspaceCollection[]>('/api/workspace/collections');
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

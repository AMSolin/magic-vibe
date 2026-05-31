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

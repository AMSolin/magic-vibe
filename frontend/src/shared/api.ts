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

export type CollectionItem = {
  id: number;
  card_uuid: string;
  card: Card;
  quantity: number;
  condition_code: string;
  foil: boolean;
  language: string;
  created_at: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
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

export function listCollection(): Promise<CollectionItem[]> {
  return request<CollectionItem[]>('/api/collection');
}

export function addCollectionItem(payload: CollectionItemCreate): Promise<CollectionItem> {
  return request<CollectionItem>('/api/collection', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateCollectionItem(
  itemId: number,
  payload: CollectionItemUpdate,
): Promise<CollectionItem> {
  return request<CollectionItem>(`/api/collection/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteCollectionItem(itemId: number): Promise<void> {
  return request<void>(`/api/collection/${itemId}`, {
    method: 'DELETE',
  });
}

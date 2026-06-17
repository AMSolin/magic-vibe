import { createRouter, createWebHistory } from 'vue-router';

import CollectionWorkspacePage from '@/pages/CollectionWorkspacePage.vue';
import DecksPage from '@/pages/DecksPage.vue';
import ImportPage from '@/pages/ImportPage.vue';
import AdminPage from '@/pages/AdminPage.vue';
import PlayersPage from '@/pages/PlayersPage.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: CollectionWorkspacePage },
    { path: '/players', component: PlayersPage },
    { path: '/decks', component: DecksPage },
    { path: '/import', component: ImportPage },
    { path: '/admin', component: AdminPage },
  ],
});

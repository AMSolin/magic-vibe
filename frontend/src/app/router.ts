import { createRouter, createWebHistory } from 'vue-router';

import CardsPage from '@/pages/CardsPage.vue';
import CollectionPage from '@/pages/CollectionPage.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: CollectionPage },
    { path: '/cards', component: CardsPage },
  ],
});


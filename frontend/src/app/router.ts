import { createRouter, createWebHistory } from 'vue-router';

import CardsPage from '@/pages/CardsPage.vue';
import CardsWorkflowComparePage from '@/pages/CardsWorkflowComparePage.vue';
import DecksPage from '@/pages/DecksPage.vue';
import AdminPage from '@/pages/AdminPage.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: CardsWorkflowComparePage },
    { path: '/cards', component: CardsPage },
    { path: '/cards-workflow-compare', redirect: '/' },
    { path: '/decks', component: DecksPage },
    { path: '/admin', component: AdminPage },
  ],
});

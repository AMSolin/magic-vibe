<script setup lang="ts">
import { ref, watch } from 'vue';
import Button from 'primevue/button';
import Menubar from 'primevue/menubar';

const themeStorageKey = 'magic-vibe-theme';
const isDarkTheme = ref(localStorage.getItem(themeStorageKey) === 'dark');

watch(
  isDarkTheme,
  (isDark) => {
    document.documentElement.classList.toggle('app-dark', isDark);
    localStorage.setItem(themeStorageKey, isDark ? 'dark' : 'light');
  },
  { immediate: true },
);

const items = [
  { label: 'Collection', icon: 'pi pi-box', route: '/' },
  { label: 'Players', icon: 'pi pi-users', route: '/players' },
  { label: 'Decks', icon: 'pi pi-book', route: '/decks' },
  { label: 'Import', icon: 'pi pi-file-import', route: '/import' },
  { label: 'Admin', icon: 'pi pi-cog', route: '/admin' },
];
</script>

<template>
  <div class="app-shell">
    <Menubar :model="items">
      <template #start>
        <RouterLink class="brand" to="/">Magic Vibe</RouterLink>
      </template>
      <template #item="{ item, props }">
        <RouterLink v-if="item.route" v-slot="{ href, navigate }" :to="item.route" custom>
          <a :href="href" v-bind="props.action" @click="navigate">
            <span :class="item.icon" />
            <span>{{ item.label }}</span>
          </a>
        </RouterLink>
      </template>
      <template #end>
        <Button
          :aria-label="isDarkTheme ? 'Switch to light theme' : 'Switch to dark theme'"
          :icon="isDarkTheme ? 'pi pi-sun' : 'pi pi-moon'"
          :title="isDarkTheme ? 'Switch to light theme' : 'Switch to dark theme'"
          rounded
          text
          @click="isDarkTheme = !isDarkTheme"
        />
      </template>
    </Menubar>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

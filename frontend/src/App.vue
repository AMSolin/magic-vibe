<script setup lang="ts">
import Menubar from 'primevue/menubar';

const items = [
  { label: 'Collection', icon: 'pi pi-box', route: '/' },
  { label: 'Cards', icon: 'pi pi-search', route: '/cards' },
];
</script>

<template>
  <div class="app-shell">
    <Menubar :model="items">
      <template #start>
        <RouterLink class="brand" to="/">Magic Explorer</RouterLink>
      </template>
      <template #item="{ item, props }">
        <RouterLink v-if="item.route" v-slot="{ href, navigate }" :to="item.route" custom>
          <a :href="href" v-bind="props.action" @click="navigate">
            <span :class="item.icon" />
            <span>{{ item.label }}</span>
          </a>
        </RouterLink>
      </template>
    </Menubar>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

